from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.oikb import (
    OIKBApproval,
    OIKBChangeLog,
    OIKBDefinition,
    OIKBDefinitionSource,
    OIKBDefinitionVersion,
    OIKBEvidenceRequirement,
    OIKBInputRequirement,
    OIKBParameter,
    OIKBSource,
    OIKBValidationCase,
    OIKBValidationResult,
)
from app.registries.calculation_registry import CalculationOperation
from app.schemas.oikb import (
    AnalyticalLevel,
    DefinitionCreate,
    DefinitionUpdate,
    DefinitionVersionCreate,
    ExecutionPackage,
    GovernanceAction,
    LifecycleStatus,
    ResolutionRead,
    ResolveRequest,
    SourceCreate,
    SourceLinkCreate,
    ValidationCaseCreate,
)


class OIKBError(ValueError):
    code = "OIKB_ERROR"
    http_status = 422


class OIKBNotFoundError(OIKBError):
    code = "OIKB_NOT_FOUND"
    http_status = 404


class OIKBConflictError(OIKBError):
    code = "OIKB_CONFLICT"
    http_status = 409


class OIKBAuthorizationError(OIKBError):
    code = "OIKB_ACCESS_DENIED"
    http_status = 403


class OIKBUnsupportedError(OIKBError):
    code = "OIKB_UNSUPPORTED"
    http_status = 422


class OIKBImmutableError(OIKBConflictError):
    code = "OIKB_ACTIVE_VERSION_IMMUTABLE"


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _fingerprint(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _version_tuple(value: str) -> tuple[int, int, int]:
    if not re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", value):
        raise OIKBError("Semantic version must use MAJOR.MINOR.PATCH")
    return tuple(int(item) for item in value.split("."))  # type: ignore[return-value]


class FormulaValidationService:
    supported_operations = {item.value for item in CalculationOperation}
    executable_levels = {AnalyticalLevel.ARITHMETIC.value, AnalyticalLevel.RULE_BASED.value}

    def validate(
        self,
        definition: OIKBDefinition,
        payload: DefinitionVersionCreate,
    ) -> str:
        expression = payload.expression_schema.model_dump(mode="json")
        operation = str(expression["operation"])
        if definition.analytical_level in self.executable_levels:
            if operation not in self.supported_operations:
                raise OIKBUnsupportedError(
                    f"Operation {operation!r} is not supported by the WP-2.07 execution boundary"
                )
        input_codes = {item.input_code for item in payload.input_requirements}
        unknown_inputs = set(expression["inputs"]) - input_codes
        if unknown_inputs:
            raise OIKBError(
                f"Expression references undeclared inputs: {', '.join(sorted(unknown_inputs))}"
            )
        parameter_codes = {item.parameter_code for item in payload.parameters}
        unknown_parameters = set(expression["parameters"]) - parameter_codes
        if unknown_parameters:
            raise OIKBError(
                "Expression references undeclared parameters: "
                + ", ".join(sorted(unknown_parameters))
            )
        units = {
            item.expected_unit
            for item in payload.input_requirements
            if item.expected_unit is not None
        }
        if operation in {
            CalculationOperation.SUM.value,
            CalculationOperation.AVERAGE.value,
            CalculationOperation.MINIMUM.value,
            CalculationOperation.MAXIMUM.value,
            CalculationOperation.ABSOLUTE_VARIANCE.value,
            CalculationOperation.RECONCILIATION.value,
        }:
            if len(units) > 1 or (units and payload.output_unit not in units):
                raise OIKBError("Input and output units are incompatible")
        currencies = {
            item.currency_code
            for item in payload.input_requirements
            if item.currency_code is not None
        }
        if len(currencies) > 1:
            raise OIKBError("Cross-currency aggregation requires a governed conversion rule")
        if currencies and payload.currency_code not in currencies:
            raise OIKBError("Input and output currency codes must match")
        if payload.currency_code is not None and payload.output_type != "currency":
            raise OIKBError("currency_code requires output_type='currency'")
        content = {
            "semantic_version": payload.semantic_version,
            "expression_schema": expression,
            "output_type": payload.output_type,
            "output_unit": payload.output_unit,
            "currency_code": payload.currency_code,
            "rounding_policy": payload.rounding_policy,
            "null_policy": payload.null_policy,
            "zero_denominator_policy": payload.zero_denominator_policy,
            "trust_requirement": payload.trust_requirement,
            "readiness_requirement": payload.readiness_requirement,
            "parameters": [item.model_dump(mode="json") for item in payload.parameters],
            "input_requirements": [
                item.model_dump(mode="json") for item in payload.input_requirements
            ],
            "evidence_requirements": [
                item.model_dump(mode="json") for item in payload.evidence_requirements
            ],
        }
        return _fingerprint(content)


class DefinitionRegistryService:
    def __init__(self, formula_validator: FormulaValidationService | None = None) -> None:
        self.formula_validator = formula_validator or FormulaValidationService()

    def create(self, db: Session, payload: DefinitionCreate, actor_id: UUID) -> OIKBDefinition:
        scope_key = self._scope_key(payload)
        existing = db.scalar(
            select(OIKBDefinition).where(
                OIKBDefinition.stable_code == payload.stable_code,
                OIKBDefinition.scope_key == scope_key,
            )
        )
        if existing is not None:
            raise OIKBConflictError("Stable code already exists in this specialization scope")
        definition_data = payload.model_dump(
            mode="python",
            exclude={"knowledge_class", "analytical_level", "scope_type"},
        )
        definition = OIKBDefinition(
            **definition_data,
            knowledge_class=payload.knowledge_class.value,
            analytical_level=payload.analytical_level.value,
            scope_type=payload.scope_type.value,
            scope_key=scope_key,
            created_by=actor_id,
        )
        db.add(definition)
        db.flush()
        self._audit(db, definition, None, "definition_created", None, None, actor_id, "created")
        db.commit()
        db.refresh(definition)
        return definition

    @staticmethod
    def _scope_key(payload: DefinitionCreate) -> str:
        if payload.owner_organization_id is not None:
            return f"organization:{payload.owner_organization_id}"
        if payload.region_code is not None:
            return f"regional:{payload.region_code.upper()}"
        if payload.industry_pack_code is not None:
            return f"industry:{payload.industry_pack_code.upper()}"
        return "shared_core"

    def get(self, db: Session, definition_id: UUID, organization_id: UUID | None) -> OIKBDefinition:
        definition = db.scalar(
            select(OIKBDefinition).where(
                OIKBDefinition.id == definition_id,
                or_(
                    OIKBDefinition.owner_organization_id.is_(None),
                    OIKBDefinition.owner_organization_id == organization_id,
                ),
            )
        )
        if definition is None:
            raise OIKBNotFoundError("Definition not found")
        return definition

    def list_definitions(
        self,
        db: Session,
        organization_id: UUID | None,
        *,
        page: int,
        page_size: int,
    ) -> tuple[list[OIKBDefinition], int]:
        tenant_filter = or_(
            OIKBDefinition.owner_organization_id.is_(None),
            OIKBDefinition.owner_organization_id == organization_id,
        )
        total = (
            db.scalar(select(func.count()).select_from(OIKBDefinition).where(tenant_filter)) or 0
        )
        items = list(
            db.scalars(
                select(OIKBDefinition)
                .where(tenant_filter)
                .order_by(OIKBDefinition.stable_code, OIKBDefinition.scope_type)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return items, total

    def update(
        self,
        db: Session,
        definition_id: UUID,
        organization_id: UUID | None,
        payload: DefinitionUpdate,
        actor_id: UUID,
    ) -> OIKBDefinition:
        definition = self.get(db, definition_id, organization_id)
        if definition.is_system_definition and organization_id is not None:
            raise OIKBAuthorizationError("System definitions require platform administration")
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(definition, key, value)
        definition.updated_at = datetime.now(UTC)
        self._audit(db, definition, None, "definition_updated", None, None, actor_id, "updated")
        db.commit()
        db.refresh(definition)
        return definition

    def create_version(
        self,
        db: Session,
        definition_id: UUID,
        organization_id: UUID | None,
        payload: DefinitionVersionCreate,
        actor_id: UUID,
    ) -> OIKBDefinitionVersion:
        definition = self.get(db, definition_id, organization_id)
        requested = _version_tuple(payload.semantic_version)
        existing_versions = list(
            db.scalars(
                select(OIKBDefinitionVersion).where(
                    OIKBDefinitionVersion.definition_id == definition.id
                )
            )
        )
        if any(item.semantic_version == payload.semantic_version for item in existing_versions):
            raise OIKBConflictError("Semantic version already exists")
        if existing_versions and requested <= max(
            _version_tuple(item.semantic_version) for item in existing_versions
        ):
            raise OIKBError("New semantic version must be greater than all existing versions")
        fingerprint = self.formula_validator.validate(definition, payload)
        if any(item.fingerprint == fingerprint for item in existing_versions):
            raise OIKBConflictError("Duplicate definition version content")
        version = OIKBDefinitionVersion(
            definition_id=definition.id,
            semantic_version=payload.semantic_version,
            lifecycle_status=LifecycleStatus.DRAFT.value,
            quality_level=payload.quality_level.value,
            effective_from=payload.effective_from,
            effective_to=payload.effective_to,
            expression_schema=payload.expression_schema.model_dump(mode="json"),
            output_type=payload.output_type,
            output_unit=payload.output_unit,
            currency_code=payload.currency_code,
            rounding_policy=payload.rounding_policy,
            null_policy=payload.null_policy,
            zero_denominator_policy=payload.zero_denominator_policy,
            trust_requirement=payload.trust_requirement,
            readiness_requirement=payload.readiness_requirement,
            fingerprint=fingerprint,
            created_by=actor_id,
        )
        db.add(version)
        db.flush()
        for parameter in payload.parameters:
            db.add(OIKBParameter(definition_version_id=version.id, **parameter.model_dump()))
        for input_requirement in payload.input_requirements:
            db.add(
                OIKBInputRequirement(
                    definition_version_id=version.id, **input_requirement.model_dump()
                )
            )
        for evidence_requirement in payload.evidence_requirements:
            db.add(
                OIKBEvidenceRequirement(
                    definition_version_id=version.id, **evidence_requirement.model_dump()
                )
            )
        self._audit(
            db,
            definition,
            version,
            "version_created",
            None,
            LifecycleStatus.DRAFT.value,
            actor_id,
            "created",
        )
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise OIKBConflictError("Definition version conflicts with existing data") from exc
        db.refresh(version)
        return version

    def get_version(
        self, db: Session, version_id: UUID, organization_id: UUID | None
    ) -> OIKBDefinitionVersion:
        version = db.scalar(
            select(OIKBDefinitionVersion)
            .join(OIKBDefinition)
            .where(
                OIKBDefinitionVersion.id == version_id,
                or_(
                    OIKBDefinition.owner_organization_id.is_(None),
                    OIKBDefinition.owner_organization_id == organization_id,
                ),
            )
        )
        if version is None:
            raise OIKBNotFoundError("Definition version not found")
        return version

    def list_versions(
        self, db: Session, definition_id: UUID, organization_id: UUID | None
    ) -> list[OIKBDefinitionVersion]:
        definition = self.get(db, definition_id, organization_id)
        return list(
            db.scalars(
                select(OIKBDefinitionVersion)
                .where(OIKBDefinitionVersion.definition_id == definition.id)
                .order_by(OIKBDefinitionVersion.created_at)
            )
        )

    @staticmethod
    def _audit(
        db: Session,
        definition: OIKBDefinition,
        version: OIKBDefinitionVersion | None,
        action: str,
        previous: str | None,
        new: str | None,
        actor_id: UUID,
        reason: str,
    ) -> None:
        db.add(
            OIKBChangeLog(
                definition_id=definition.id,
                definition_version_id=version.id if version else None,
                action=action,
                previous_state=previous,
                new_state=new,
                actor_id=actor_id,
                reason=reason,
            )
        )


class GovernanceService:
    transitions = {
        LifecycleStatus.DRAFT: {LifecycleStatus.IN_REVIEW},
        LifecycleStatus.IN_REVIEW: {LifecycleStatus.VALIDATED, LifecycleStatus.REJECTED},
        LifecycleStatus.VALIDATED: {LifecycleStatus.APPROVED, LifecycleStatus.REJECTED},
        LifecycleStatus.APPROVED: {LifecycleStatus.ACTIVE, LifecycleStatus.REJECTED},
        LifecycleStatus.ACTIVE: {LifecycleStatus.DEPRECATED},
        LifecycleStatus.DEPRECATED: {LifecycleStatus.RETIRED},
        LifecycleStatus.REJECTED: set(),
        LifecycleStatus.RETIRED: set(),
    }

    def __init__(self, registry: DefinitionRegistryService | None = None) -> None:
        self.registry = registry or DefinitionRegistryService()

    def transition(
        self,
        db: Session,
        version_id: UUID,
        organization_id: UUID | None,
        target: LifecycleStatus,
        action: GovernanceAction,
        actor_id: UUID,
    ) -> OIKBDefinitionVersion:
        version = self.registry.get_version(db, version_id, organization_id)
        definition = version.definition
        current = LifecycleStatus(version.lifecycle_status)
        if target not in self.transitions[current]:
            raise OIKBConflictError(f"Invalid lifecycle transition: {current} -> {target}")
        if target == LifecycleStatus.VALIDATED and not version.validation_satisfied:
            raise OIKBConflictError("Successful validation is required")
        if target == LifecycleStatus.APPROVED:
            db.add(
                OIKBApproval(
                    definition_version_id=version.id,
                    approval_role="knowledge_approver",
                    approver_id=actor_id,
                    decision="approved",
                    notes=action.notes,
                )
            )
        if target == LifecycleStatus.ACTIVE:
            approved = db.scalar(
                select(OIKBApproval.id).where(
                    OIKBApproval.definition_version_id == version.id,
                    OIKBApproval.decision == "approved",
                )
            )
            if approved is None or not version.validation_satisfied:
                raise OIKBConflictError("Approval and successful validation are required")
            active = db.scalar(
                select(OIKBDefinitionVersion).where(
                    OIKBDefinitionVersion.definition_id == definition.id,
                    OIKBDefinitionVersion.lifecycle_status == LifecycleStatus.ACTIVE.value,
                    OIKBDefinitionVersion.id != version.id,
                )
            )
            if active is not None:
                raise OIKBConflictError("Only one active version is permitted per scope")
            version.effective_from = (
                action.effective_from or version.effective_from or datetime.now(UTC)
            )
            version.activated_by = actor_id
            version.activated_at = datetime.now(UTC)
        version.lifecycle_status = target.value
        DefinitionRegistryService._audit(
            db,
            definition,
            version,
            f"lifecycle_{target.value}",
            current.value,
            target.value,
            actor_id,
            action.reason,
        )
        db.commit()
        db.refresh(version)
        return version

    def mark_validated(
        self,
        db: Session,
        version_id: UUID,
        organization_id: UUID | None,
        actor_id: UUID,
    ) -> OIKBDefinitionVersion:
        version = self.registry.get_version(db, version_id, organization_id)
        if version.lifecycle_status != LifecycleStatus.IN_REVIEW.value:
            raise OIKBConflictError("Only in-review versions may be validated")
        if not version.validation_satisfied:
            raise OIKBConflictError("Successful validation cases are required")
        return self.transition(
            db,
            version_id,
            organization_id,
            LifecycleStatus.VALIDATED,
            GovernanceAction(reason="validation cases satisfied"),
            actor_id,
        )


@dataclass(frozen=True)
class ResolvedKnowledge:
    definition: OIKBDefinition
    version: OIKBDefinitionVersion
    trace: ResolutionRead


class KnowledgeResolutionService:
    precedence = ("organization", "regional", "industry", "shared_core")

    def resolve(self, db: Session, request: ResolveRequest) -> ResolvedKnowledge | None:
        at = request.effective_at or datetime.now(UTC)
        candidates = list(
            db.execute(
                select(OIKBDefinition, OIKBDefinitionVersion)
                .join(OIKBDefinitionVersion)
                .where(
                    OIKBDefinition.stable_code == request.stable_code,
                    OIKBDefinitionVersion.lifecycle_status == LifecycleStatus.ACTIVE.value,
                    or_(
                        OIKBDefinitionVersion.effective_from.is_(None),
                        OIKBDefinitionVersion.effective_from <= at,
                    ),
                    or_(
                        OIKBDefinitionVersion.effective_to.is_(None),
                        OIKBDefinitionVersion.effective_to > at,
                    ),
                    or_(
                        OIKBDefinition.owner_organization_id.is_(None),
                        OIKBDefinition.owner_organization_id == request.organization_id,
                    ),
                )
            )
        )
        fallback: list[str] = []
        for scope in self.precedence:
            for definition, version in candidates:
                eligible = (
                    (
                        scope == "organization"
                        and definition.owner_organization_id == request.organization_id
                    )
                    or (
                        scope == "regional"
                        and definition.scope_type == "regional"
                        and definition.region_code == request.region_code
                    )
                    or (
                        scope == "industry"
                        and definition.scope_type == "industry"
                        and definition.industry_pack_code == request.industry_pack_code
                    )
                    or (scope == "shared_core" and definition.scope_type == "shared_core")
                )
                if eligible:
                    trace = ResolutionRead(
                        status="resolved",
                        definition_id=definition.id,
                        definition_version_id=version.id,
                        stable_code=definition.stable_code,
                        semantic_version=version.semantic_version,
                        scope_selected=definition.scope_type,
                        resolution_path=list(self.precedence),
                        fallback_steps=fallback,
                        warnings=[],
                        effective_from=version.effective_from,
                        effective_to=version.effective_to,
                        fingerprint=version.fingerprint,
                    )
                    return ResolvedKnowledge(definition, version, trace)
            fallback.append(f"{scope}:no_eligible_active_definition")
        return None

    def resolve_response(self, db: Session, request: ResolveRequest) -> ResolutionRead:
        resolved = self.resolve(db, request)
        if resolved is not None:
            return resolved.trace
        return ResolutionRead(
            status="unresolved",
            definition_id=None,
            definition_version_id=None,
            stable_code=request.stable_code,
            semantic_version=None,
            scope_selected=None,
            resolution_path=list(self.precedence),
            fallback_steps=[f"{scope}:no_eligible_active_definition" for scope in self.precedence],
            warnings=["No eligible governed definition was found"],
            effective_from=None,
            effective_to=None,
            fingerprint=None,
        )


class SourceCitationService:
    def create(
        self, db: Session, payload: SourceCreate, actor_organization_id: UUID | None
    ) -> OIKBSource:
        if payload.owner_organization_id != actor_organization_id:
            raise OIKBAuthorizationError("Source owner must match the authorized organization")
        source = OIKBSource(**payload.model_dump())
        db.add(source)
        db.commit()
        db.refresh(source)
        return source

    def list(self, db: Session, organization_id: UUID | None) -> list[OIKBSource]:
        return list(
            db.scalars(
                select(OIKBSource)
                .where(
                    or_(
                        OIKBSource.owner_organization_id.is_(None),
                        OIKBSource.owner_organization_id == organization_id,
                    )
                )
                .order_by(OIKBSource.title)
            )
        )

    def link(
        self,
        db: Session,
        version: OIKBDefinitionVersion,
        payload: SourceLinkCreate,
        organization_id: UUID | None,
    ) -> OIKBDefinitionSource:
        source = db.scalar(
            select(OIKBSource).where(
                OIKBSource.id == payload.source_id,
                or_(
                    OIKBSource.owner_organization_id.is_(None),
                    OIKBSource.owner_organization_id == organization_id,
                ),
            )
        )
        if source is None:
            raise OIKBNotFoundError("Source not found")
        link = OIKBDefinitionSource(
            definition_version_id=version.id, **payload.model_dump(mode="python")
        )
        db.add(link)
        db.commit()
        db.refresh(link)
        return link


class KnowledgeValidationService:
    engine_version = "wp-2.07-bounded-1.0"

    def create_case(
        self,
        db: Session,
        version: OIKBDefinitionVersion,
        payload: ValidationCaseCreate,
    ) -> OIKBValidationCase:
        if version.lifecycle_status == LifecycleStatus.ACTIVE.value:
            raise OIKBImmutableError("Active version validation cases are immutable")
        case = OIKBValidationCase(
            definition_version_id=version.id, **payload.model_dump(mode="python")
        )
        db.add(case)
        db.commit()
        db.refresh(case)
        return case

    def list_cases(self, db: Session, version_id: UUID) -> list[OIKBValidationCase]:
        return list(
            db.scalars(
                select(OIKBValidationCase)
                .where(OIKBValidationCase.definition_version_id == version_id)
                .order_by(OIKBValidationCase.case_code)
            )
        )

    def run(
        self, db: Session, version: OIKBDefinitionVersion, actor_id: UUID
    ) -> list[OIKBValidationResult]:
        cases = self.list_cases(db, version.id)
        if not cases:
            raise OIKBConflictError("At least one validation case is required")
        results: list[OIKBValidationResult] = []
        all_passed = True
        for case in cases:
            actual, error = self._execute(version, case.input_payload)
            passed = error is None and self._matches(actual, case.expected_output, case.tolerance)
            all_passed = all_passed and passed
            result = OIKBValidationResult(
                definition_version_id=version.id,
                validation_case_id=case.id,
                status="passed" if passed else "failed",
                actual_output=actual,
                variance=None,
                executed_by=actor_id,
                engine_version=self.engine_version,
                definition_fingerprint=version.fingerprint,
                error_code="VALIDATION_EXECUTION_FAILED" if error else None,
                error_message=error,
            )
            db.add(result)
            results.append(result)
        version.validation_satisfied = all_passed
        db.commit()
        for result in results:
            db.refresh(result)
        return results

    @staticmethod
    def _execute(
        version: OIKBDefinitionVersion, payload: dict[str, object]
    ) -> tuple[object | None, str | None]:
        operation = str(version.expression_schema["operation"])
        values = payload.get("values")
        try:
            numeric = [Decimal(str(item)) for item in values] if isinstance(values, list) else []
            if operation == "count":
                return len(values) if isinstance(values, list) else 0, None
            if operation == "distinct_count":
                return len(set(str(item) for item in values)) if isinstance(
                    values, list
                ) else 0, None
            if operation == "sum":
                return str(sum(numeric, Decimal("0"))), None
            if operation == "average":
                return str(sum(numeric) / len(numeric)), None
            if operation == "minimum":
                return str(min(numeric)), None
            if operation == "maximum":
                return str(max(numeric)), None
            left = Decimal(str(payload["left"]))
            right = Decimal(str(payload["right"]))
            if operation in {"absolute_variance", "reconciliation"}:
                return str(left - right), None
            if operation == "ratio":
                return str(left / right), None
            if operation in {"percentage", "percentage_variance"}:
                numerator = left if operation == "percentage" else left - right
                return str((numerator / right) * 100), None
            return None, "Unsupported operation"
        except (KeyError, InvalidOperation, ZeroDivisionError, ValueError) as exc:
            return None, type(exc).__name__

    @staticmethod
    def _matches(actual: object, expected: object, tolerance: str | None) -> bool:
        if tolerance is None:
            return str(actual) == str(expected)
        try:
            return abs(Decimal(str(actual)) - Decimal(str(expected))) <= Decimal(tolerance)
        except (InvalidOperation, TypeError):
            return False


class ExecutionPackageExportService:
    executable_levels = {"arithmetic", "rule_based"}

    def export(
        self,
        db: Session,
        version: OIKBDefinitionVersion,
        resolution_metadata: dict[str, object] | None = None,
    ) -> ExecutionPackage:
        definition = version.definition
        if version.lifecycle_status != LifecycleStatus.ACTIVE.value:
            raise OIKBConflictError("Only active definitions may be exported")
        if definition.analytical_level not in self.executable_levels:
            raise OIKBUnsupportedError(
                f"Analytical level {definition.analytical_level} is not executable in WP-2.10"
            )
        source_rows = db.execute(
            select(OIKBDefinitionSource, OIKBSource)
            .join(OIKBSource)
            .where(OIKBDefinitionSource.definition_version_id == version.id)
        )
        return ExecutionPackage(
            stable_code=definition.stable_code,
            semantic_version=version.semantic_version,
            knowledge_class=definition.knowledge_class,
            analytical_level=definition.analytical_level,
            operation=str(version.expression_schema["operation"]),
            parameters=[
                {
                    "parameter_code": item.parameter_code,
                    "data_type": item.data_type,
                    "required": item.required,
                    "unit": item.unit,
                }
                for item in version.parameters
            ],
            input_requirements=[
                {
                    "input_code": item.input_code,
                    "canonical_entity": item.canonical_entity,
                    "canonical_field": item.canonical_field,
                    "expected_type": item.expected_type,
                    "expected_unit": item.expected_unit,
                    "currency_code": item.currency_code,
                    "required": item.required,
                }
                for item in version.input_requirements
            ],
            output_contract={
                "type": version.output_type,
                "unit": version.output_unit,
                "currency_code": version.currency_code,
                "rounding_policy": version.rounding_policy,
                "null_policy": version.null_policy,
                "zero_denominator_policy": version.zero_denominator_policy,
            },
            trust_requirement=version.trust_requirement,
            readiness_requirement=version.readiness_requirement,
            evidence_requirements=[
                {
                    "evidence_type": item.evidence_type,
                    "requirement_code": item.requirement_code,
                    "required": item.required,
                    "minimum_count": item.minimum_count,
                }
                for item in version.evidence_requirements
            ],
            fingerprint=version.fingerprint,
            provenance_references=[
                {
                    "source_id": str(source.id),
                    "title": source.title,
                    "authority_level": source.authority_level,
                    "relationship_type": link.relationship_type,
                    "is_primary": link.is_primary,
                }
                for link, source in source_rows
            ],
            resolution_metadata=resolution_metadata or {},
        )


definition_registry_service = DefinitionRegistryService()
governance_service = GovernanceService(definition_registry_service)
knowledge_resolution_service = KnowledgeResolutionService()
source_citation_service = SourceCitationService()
knowledge_validation_service = KnowledgeValidationService()
execution_package_export_service = ExecutionPackageExportService()
