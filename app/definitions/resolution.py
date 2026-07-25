from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from app.registries.calculation_registry import (
    CalculationDefinition,
    DefinitionNotFoundError,
    default_calculation_registry,
)
from app.registries.rule_registry import RuleDefinition, default_rule_registry
from app.schemas.intelligence import ExecutionType
from app.schemas.orchestration import OrchestrationAnalyticalLevel


class DefinitionKnowledgeClass(StrEnum):
    CALCULATION = "calculation"
    DETERMINISTIC_RULE = "deterministic_rule"
    STATISTICAL_METHOD = "statistical_method"
    FORECASTING_METHOD = "forecasting_method"


@dataclass(frozen=True)
class PolicyReference:
    code: str
    version: str


@dataclass(frozen=True)
class ResolvedDefinition:
    code: str
    version: str
    knowledge_class: DefinitionKnowledgeClass
    analytical_level: OrchestrationAnalyticalLevel
    required_readiness_level: OrchestrationAnalyticalLevel
    required_engine_capability: str
    is_active: bool
    publication_eligible: bool
    sufficiency_policy: PolicyReference
    escalation_policy: PolicyReference
    evidence_policy: PolicyReference
    scope_metadata: dict[str, object]
    definition_fingerprint: str


class DefinitionResolutionError(ValueError):
    pass


class DefinitionResolver(Protocol):
    def resolve(
        self,
        code: str,
        version: str,
        execution_type: ExecutionType,
        *,
        db: Session | None = None,
        organization_id: UUID | None = None,
        effective_at: datetime | None = None,
    ) -> ResolvedDefinition: ...


def _fingerprint(value: object) -> str:
    encoded = json.dumps(value, default=str, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


class CodeBackedOIKBDefinitionResolver:
    """Temporary adapter over WP-2.07 registries.

    A persisted OIKB can replace this implementation without changing the
    orchestration service or its normalized definition contract.
    """

    def __init__(self) -> None:
        self.calculations = default_calculation_registry()
        self.rules = default_rule_registry()

    def resolve(
        self,
        code: str,
        version: str,
        execution_type: ExecutionType,
        *,
        db: Session | None = None,
        organization_id: UUID | None = None,
        effective_at: datetime | None = None,
    ) -> ResolvedDefinition:
        del db, organization_id, effective_at
        try:
            if execution_type == ExecutionType.CALCULATION:
                calculation = self.calculations.get(code, version)
                return self._calculation(calculation)
            rule = self.rules.get(code, version)
            return self._rule(rule)
        except DefinitionNotFoundError as exc:
            raise DefinitionResolutionError("Definition is not eligible") from exc

    @staticmethod
    def _calculation(definition: CalculationDefinition) -> ResolvedDefinition:
        return ResolvedDefinition(
            code=definition.code,
            version=definition.version,
            knowledge_class=DefinitionKnowledgeClass.CALCULATION,
            analytical_level=OrchestrationAnalyticalLevel.ARITHMETIC,
            required_readiness_level=OrchestrationAnalyticalLevel.ARITHMETIC,
            required_engine_capability="bounded_arithmetic",
            is_active=definition.status == "active",
            publication_eligible=definition.status == "active",
            sufficiency_policy=PolicyReference("DETERMINISTIC_EXECUTION_SUFFICIENCY", "1.0"),
            escalation_policy=PolicyReference("OIKB_BOUNDED_ESCALATION", "1.0"),
            evidence_policy=PolicyReference(
                definition.evidence_contract or "WP207_EXECUTION_EVIDENCE",
                "1.0",
            ),
            scope_metadata={
                "canonical_fields": list(definition.canonical_fields),
                "unit_policy": definition.unit_policy,
                "currency_policy": definition.currency_policy,
                "scope_correction": definition.scope_correction,
                "domain_owner": definition.domain_owner,
            },
            definition_fingerprint=_fingerprint(asdict(definition)),
        )

    @staticmethod
    def _rule(definition: RuleDefinition) -> ResolvedDefinition:
        return ResolvedDefinition(
            code=definition.code,
            version=definition.version,
            knowledge_class=DefinitionKnowledgeClass.DETERMINISTIC_RULE,
            analytical_level=OrchestrationAnalyticalLevel.RULE_BASED,
            required_readiness_level=OrchestrationAnalyticalLevel.ARITHMETIC,
            required_engine_capability="bounded_deterministic_rule",
            is_active=definition.status == "active",
            publication_eligible=definition.status == "active",
            sufficiency_policy=PolicyReference("DETERMINISTIC_EXECUTION_SUFFICIENCY", "1.0"),
            escalation_policy=PolicyReference("OIKB_BOUNDED_ESCALATION", "1.0"),
            evidence_policy=PolicyReference("WP207_RULE_EXECUTION_EVIDENCE", "1.0"),
            scope_metadata={
                "required_parameters": list(definition.required_parameters),
                "operator": definition.operator.value,
            },
            definition_fingerprint=_fingerprint(asdict(definition)),
        )


class GovernedOIKBDefinitionResolver:
    """Database-backed resolver for active governed OIKB definitions."""

    def resolve(
        self,
        code: str,
        version: str,
        execution_type: ExecutionType,
        *,
        db: Session | None = None,
        organization_id: UUID | None = None,
        effective_at: datetime | None = None,
    ) -> ResolvedDefinition:
        if db is None or organization_id is None:
            raise DefinitionResolutionError("Governed resolution requires tenant context")
        if code != code.upper() or "." not in code:
            raise DefinitionResolutionError("Legacy identifier is not a governed stable code")
        from app.schemas.oikb import ResolveRequest
        from app.services.oikb_service import knowledge_resolution_service

        resolved = knowledge_resolution_service.resolve(
            db,
            ResolveRequest(
                organization_id=organization_id,
                stable_code=code,
                effective_at=effective_at,
            ),
        )
        if resolved is None or resolved.version.semantic_version != version:
            raise DefinitionResolutionError("Definition is not eligible")
        definition = resolved.definition
        definition_version = resolved.version
        expected_type = (
            ExecutionType.RULE
            if definition.analytical_level == OrchestrationAnalyticalLevel.RULE_BASED.value
            else ExecutionType.CALCULATION
        )
        if execution_type != expected_type:
            raise DefinitionResolutionError("Definition execution type is incompatible")
        knowledge_class = (
            DefinitionKnowledgeClass.DETERMINISTIC_RULE
            if expected_type == ExecutionType.RULE
            else (
                DefinitionKnowledgeClass.FORECASTING_METHOD
                if definition.analytical_level == OrchestrationAnalyticalLevel.FORECASTING.value
                else (
                    DefinitionKnowledgeClass.STATISTICAL_METHOD
                    if definition.analytical_level == OrchestrationAnalyticalLevel.STATISTICAL.value
                    else DefinitionKnowledgeClass.CALCULATION
                )
            )
        )
        return ResolvedDefinition(
            code=definition.stable_code,
            version=definition_version.semantic_version,
            knowledge_class=knowledge_class,
            analytical_level=OrchestrationAnalyticalLevel(definition.analytical_level),
            required_readiness_level=OrchestrationAnalyticalLevel(
                str(
                    definition_version.readiness_requirement.get(
                        "analytical_level", OrchestrationAnalyticalLevel.ARITHMETIC.value
                    )
                )
            ),
            required_engine_capability=(
                "bounded_deterministic_rule"
                if expected_type == ExecutionType.RULE
                else (
                    "bounded_forecasting_intelligence"
                    if definition.analytical_level == OrchestrationAnalyticalLevel.FORECASTING.value
                    else (
                        "bounded_statistical_intelligence"
                        if definition.analytical_level
                        == OrchestrationAnalyticalLevel.STATISTICAL.value
                        else "bounded_arithmetic"
                    )
                )
            ),
            is_active=True,
            publication_eligible=True,
            sufficiency_policy=PolicyReference("DETERMINISTIC_EXECUTION_SUFFICIENCY", "1.0"),
            escalation_policy=PolicyReference("OIKB_BOUNDED_ESCALATION", "1.0"),
            evidence_policy=PolicyReference("OIKB_GOVERNED_EVIDENCE", "1.0"),
            scope_metadata={
                "definition_id": str(definition.id),
                "definition_version_id": str(definition_version.id),
                "scope_type": definition.scope_type,
                "resolution_path": resolved.trace.resolution_path,
                "operation": definition_version.expression_schema["operation"],
                "legacy_fallback": False,
            },
            definition_fingerprint=definition_version.fingerprint,
        )


class OIKBFirstDefinitionResolver:
    """Resolve governed knowledge first and retain an observable legacy bridge."""

    def __init__(self) -> None:
        self.governed = GovernedOIKBDefinitionResolver()
        self.legacy = CodeBackedOIKBDefinitionResolver()

    def resolve(
        self,
        code: str,
        version: str,
        execution_type: ExecutionType,
        *,
        db: Session | None = None,
        organization_id: UUID | None = None,
        effective_at: datetime | None = None,
    ) -> ResolvedDefinition:
        try:
            return self.governed.resolve(
                code,
                version,
                execution_type,
                db=db,
                organization_id=organization_id,
                effective_at=effective_at,
            )
        except DefinitionResolutionError:
            legacy = self.legacy.resolve(code, version, execution_type)
            return ResolvedDefinition(
                **{
                    **legacy.__dict__,
                    "scope_metadata": {
                        **legacy.scope_metadata,
                        "legacy_fallback": True,
                        "compatibility_warning": "LEGACY_CODE_BACKED_DEFINITION",
                    },
                }
            )
