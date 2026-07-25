from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import Organization, OrganizationStatus
from app.models.ingestion import Dataset, DatasetVersion
from app.models.intelligence import IntelligenceExecution, IntelligenceExecutionStatus
from app.models.orchestration import (
    EngineRegistrationStatus,
    IntelligenceEngineRegistration,
    IntelligenceOrchestrationDecision,
    IntelligenceOrchestrationRequest,
    IntelligenceOrchestrationStatusHistory,
    IntelligenceOrchestrationStep,
    OrchestrationDecisionType,
    OrchestrationStatus,
    OrchestrationStepStatus,
)
from app.models.trust import (
    AnalyticalReadinessDecision,
    ReadinessStatus,
    TrustAssessment,
    TrustAssessmentStatus,
)
from app.registries.calculation_registry import (
    CalculationDefinition,
    DefinitionNotFoundError,
    default_calculation_registry,
)
from app.registries.engine_registry import (
    EngineCapability,
    EngineRegistry,
)
from app.registries.rule_registry import RuleDefinition, default_rule_registry
from app.schemas.intelligence import ExecutionType, IntelligenceExecutionCreate
from app.schemas.orchestration import (
    EscalationStatus,
    OrchestrationAnalyticalLevel,
    OrchestrationCreate,
    OrchestrationStepType,
    SufficiencyStatus,
)
from app.services.finding_platform_service import FindingPlatformError, finding_publication_service
from app.services.intelligence_service import intelligence_execution_service

POLICY_CODE = "PROGRESSIVE_INTELLIGENCE"
POLICY_VERSION = "1.0"


class OrchestrationError(ValueError):
    def __init__(self, code: str, message: str, *, http_status: int = 422) -> None:
        self.code = code
        self.http_status = http_status
        super().__init__(message)


class ArithmeticEngineAdapter:
    capability = EngineCapability(
        engine_code="ARITHMETIC_ENGINE",
        engine_name="Intel4Ops Arithmetic Engine",
        engine_version="1.0",
        analytical_level=OrchestrationAnalyticalLevel.ARITHMETIC,
        capability_code="bounded_arithmetic",
        implementation_reference="app.services.intelligence_service",
    )

    def can_execute(self, definition_level: OrchestrationAnalyticalLevel) -> bool:
        return definition_level == self.capability.analytical_level

    def execute(
        self,
        db: Session,
        organization_id: UUID,
        payload: OrchestrationCreate,
        actor_user_id: UUID,
        execution_idempotency_key: str,
    ) -> IntelligenceExecution:
        return intelligence_execution_service.execute(
            db,
            organization_id,
            _execution_payload(payload, ExecutionType.CALCULATION, execution_idempotency_key),
            actor_user_id,
        )


class DeterministicRuleEngineAdapter:
    capability = EngineCapability(
        engine_code="DETERMINISTIC_RULE_ENGINE",
        engine_name="Intel4Ops Deterministic Rule Engine",
        engine_version="1.0",
        analytical_level=OrchestrationAnalyticalLevel.RULE_BASED,
        capability_code="bounded_deterministic_rule",
        implementation_reference="app.services.intelligence_service",
    )

    def can_execute(self, definition_level: OrchestrationAnalyticalLevel) -> bool:
        return definition_level == self.capability.analytical_level

    def execute(
        self,
        db: Session,
        organization_id: UUID,
        payload: OrchestrationCreate,
        actor_user_id: UUID,
        execution_idempotency_key: str,
    ) -> IntelligenceExecution:
        return intelligence_execution_service.execute(
            db,
            organization_id,
            _execution_payload(payload, ExecutionType.RULE, execution_idempotency_key),
            actor_user_id,
        )


def _execution_payload(
    payload: OrchestrationCreate,
    execution_type: ExecutionType,
    idempotency_key: str,
) -> IntelligenceExecutionCreate:
    candidate = payload.finding_candidate
    return IntelligenceExecutionCreate(
        dataset_id=payload.dataset_id,
        dataset_version_id=payload.dataset_version_id,
        trust_assessment_id=payload.trust_assessment_id,
        execution_type=execution_type,
        definition_code=payload.definition_code,
        definition_version=payload.definition_version,
        idempotency_key=idempotency_key,
        records=payload.records,
        parameters=payload.parameters,
        unit=payload.unit,
        currency=payload.currency,
        exposure_value=candidate.exposure_value if candidate else None,
        exposure_currency=candidate.exposure_currency if candidate else None,
        input_period_start=candidate.occurrence_start if candidate else None,
        input_period_end=candidate.occurrence_end if candidate else None,
        evidence=payload.evidence,
    )


def default_engine_registry() -> EngineRegistry:
    registry = EngineRegistry()
    registry.register(ArithmeticEngineAdapter())
    registry.register(DeterministicRuleEngineAdapter())
    return registry


def _hash(value: object) -> str:
    encoded = json.dumps(value, default=str, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


class DefinitionResolver:
    def __init__(self) -> None:
        self.calculations = default_calculation_registry()
        self.rules = default_rule_registry()

    def resolve(
        self, code: str, version: str, execution_type: ExecutionType
    ) -> tuple[CalculationDefinition | RuleDefinition, OrchestrationAnalyticalLevel]:
        try:
            if execution_type == ExecutionType.CALCULATION:
                return (
                    self.calculations.get(code, version),
                    OrchestrationAnalyticalLevel.ARITHMETIC,
                )
            return self.rules.get(code, version), OrchestrationAnalyticalLevel.RULE_BASED
        except DefinitionNotFoundError as exc:
            raise OrchestrationError(
                "DEFINITION_NOT_ELIGIBLE",
                "Definition is not eligible",
                http_status=404,
            ) from exc


class SufficiencyPolicy:
    code = "DETERMINISTIC_EXECUTION_SUFFICIENCY"
    version = "1.0"

    @staticmethod
    def evaluate(
        execution: IntelligenceExecution,
        *,
        used_fallback: bool,
    ) -> SufficiencyStatus:
        if execution.status != IntelligenceExecutionStatus.COMPLETED.value:
            return SufficiencyStatus.NOT_EVALUATED
        if used_fallback or execution.warnings:
            return SufficiencyStatus.SUFFICIENT_WITH_LIMITATIONS
        return SufficiencyStatus.SUFFICIENT


class EscalationPolicy:
    code = "OIKB_BOUNDED_ESCALATION"
    version = "1.0"

    @staticmethod
    def evaluate(
        sufficiency: SufficiencyStatus,
        *,
        requested_level: OrchestrationAnalyticalLevel,
        selected_level: OrchestrationAnalyticalLevel,
        requested_engine_available: bool,
    ) -> EscalationStatus:
        if sufficiency == SufficiencyStatus.SUFFICIENT and requested_level == selected_level:
            return EscalationStatus.NOT_REQUIRED
        if requested_level != selected_level and not requested_engine_available:
            return EscalationStatus.NOT_SUPPORTED
        if sufficiency == SufficiencyStatus.INSUFFICIENT:
            return EscalationStatus.BLOCKED_BY_POLICY
        return EscalationStatus.NOT_REQUIRED


class OrchestrationService:
    transitions: dict[str, set[str]] = {
        OrchestrationStatus.RECEIVED.value: {
            OrchestrationStatus.VALIDATING.value,
            OrchestrationStatus.CANCELLED.value,
        },
        OrchestrationStatus.VALIDATING.value: {
            OrchestrationStatus.DECIDING.value,
            OrchestrationStatus.BLOCKED.value,
            OrchestrationStatus.UNSUPPORTED.value,
            OrchestrationStatus.FAILED.value,
        },
        OrchestrationStatus.DECIDING.value: {
            OrchestrationStatus.EXECUTING.value,
            OrchestrationStatus.BLOCKED.value,
            OrchestrationStatus.UNSUPPORTED.value,
        },
        OrchestrationStatus.EXECUTING.value: {
            OrchestrationStatus.COMPLETED.value,
            OrchestrationStatus.COMPLETED_WITH_LIMITATIONS.value,
            OrchestrationStatus.PARTIALLY_COMPLETED.value,
            OrchestrationStatus.BLOCKED.value,
            OrchestrationStatus.FAILED.value,
        },
    }

    def __init__(self, engines: EngineRegistry | None = None) -> None:
        self.engines = engines or default_engine_registry()
        self.definitions = DefinitionResolver()
        self.sufficiency = SufficiencyPolicy()
        self.escalation = EscalationPolicy()

    def orchestrate(
        self,
        db: Session,
        organization_id: UUID,
        payload: OrchestrationCreate,
        actor_user_id: UUID,
    ) -> IntelligenceOrchestrationRequest:
        context_fingerprint = self._context_fingerprint(organization_id, payload)
        existing = db.scalar(
            select(IntelligenceOrchestrationRequest).where(
                IntelligenceOrchestrationRequest.organization_id == organization_id,
                IntelligenceOrchestrationRequest.idempotency_key == payload.idempotency_key,
            )
        )
        if existing is not None:
            if existing.context_fingerprint != context_fingerprint:
                raise OrchestrationError(
                    "INVALID_IDEMPOTENCY_KEY",
                    "Idempotency key is already bound to a different request",
                    http_status=409,
                )
            return existing
        correlation = db.scalar(
            select(IntelligenceOrchestrationRequest).where(
                IntelligenceOrchestrationRequest.organization_id == organization_id,
                IntelligenceOrchestrationRequest.correlation_id == payload.correlation_id,
            )
        )
        if correlation is not None:
            raise OrchestrationError(
                "DUPLICATE_ORCHESTRATION",
                "Correlation ID is already in use",
                http_status=409,
            )
        self._validate_references(db, organization_id, payload)
        definition, definition_level = self.definitions.resolve(
            payload.definition_code,
            payload.definition_version,
            payload.execution_type,
        )
        requested_level = payload.requested_analytical_level or definition_level
        request = IntelligenceOrchestrationRequest(
            organization_id=organization_id,
            request_code=f"ORC-{uuid4().hex[:16].upper()}",
            correlation_id=payload.correlation_id,
            idempotency_key=payload.idempotency_key,
            definition_code=payload.definition_code,
            definition_version=payload.definition_version,
            requested_analytical_level=requested_level.value,
            dataset_id=payload.dataset_id,
            dataset_version_id=payload.dataset_version_id,
            dataset_reference=payload.dataset_reference,
            trust_assessment_id=payload.trust_assessment_id,
            analytical_readiness_id=payload.analytical_readiness_id,
            requested_by_user_id=actor_user_id,
            status=OrchestrationStatus.RECEIVED.value,
            publish_finding=payload.publish_finding,
            parameters_summary={
                "parameter_keys": sorted(payload.parameters),
                "parameter_fingerprint": _hash(payload.parameters),
                "record_count": len(payload.records),
                "evidence_count": len(payload.evidence),
            },
            request_context=self._bounded_context(payload.request_context),
            context_fingerprint=context_fingerprint,
            warnings=[],
            limitations=[],
        )
        db.add(request)
        db.flush()
        self._history(db, request, None, OrchestrationStatus.RECEIVED, "request_received")
        self._transition(
            db,
            request,
            OrchestrationStatus.VALIDATING,
            "validation_started",
            actor_user_id,
        )
        self._step(
            db,
            request,
            OrchestrationStepType.VALIDATION,
            OrchestrationStepStatus.COMPLETED,
            input_summary={"dataset_reference": payload.dataset_reference},
        )
        self._transition(
            db,
            request,
            OrchestrationStatus.DECIDING,
            "validation_completed",
            actor_user_id,
        )
        self._step(
            db,
            request,
            OrchestrationStepType.DEFINITION_RESOLUTION,
            OrchestrationStepStatus.COMPLETED,
            level=definition_level,
            output_summary={
                "definition_code": definition.code,
                "definition_version": definition.version,
                "definition_fingerprint": _hash(asdict(definition)),
            },
        )
        readiness = self._readiness(db, organization_id, payload, definition_level)
        self._step(
            db,
            request,
            OrchestrationStepType.TRUST_CHECK,
            OrchestrationStepStatus.COMPLETED,
            output_summary={"trust_status": self._assessment(db, organization_id, payload).status},
        )
        if readiness.readiness_status not in {
            ReadinessStatus.READY.value,
            ReadinessStatus.READY_WITH_WARNINGS.value,
        }:
            reason = (
                "TRUST_REQUIREMENT_NOT_MET"
                if readiness.readiness_status == ReadinessStatus.BLOCKED.value
                else "READINESS_REQUIREMENT_NOT_MET"
            )
            self._step(
                db,
                request,
                OrchestrationStepType.READINESS_CHECK,
                OrchestrationStepStatus.BLOCKED,
                level=definition_level,
                block_reason=reason,
                limitations=[readiness.explanation],
            )
            self._decision(
                db,
                request,
                requested_level,
                None,
                None,
                readiness,
                SufficiencyStatus.NOT_EVALUATED,
                EscalationStatus.NOT_READY,
                OrchestrationDecisionType.BLOCK,
                reason,
                readiness.explanation,
            )
            request.limitations = [readiness.explanation]
            self._transition(db, request, OrchestrationStatus.BLOCKED, reason, actor_user_id)
            request.completed_at = datetime.now(UTC)
            db.commit()
            db.refresh(request)
            return request
        self._step(
            db,
            request,
            OrchestrationStepType.READINESS_CHECK,
            OrchestrationStepStatus.COMPLETED,
            level=definition_level,
            warnings=list(readiness.warning_rule_codes),
            output_summary={"readiness_status": readiness.readiness_status},
        )
        requested_adapter = self.engines.for_level(requested_level)
        selected_level = definition_level
        used_fallback = requested_level != definition_level
        if used_fallback and not (
            definition_level == OrchestrationAnalyticalLevel.ARITHMETIC
            and payload.allow_arithmetic_fallback
        ):
            self._unsupported(
                db,
                request,
                requested_level,
                readiness,
                actor_user_id,
                "DEFINITION_LEVEL_MISMATCH",
            )
            return request
        adapter = self.engines.for_level(selected_level)
        if adapter is None:
            self._unsupported(
                db,
                request,
                requested_level,
                readiness,
                actor_user_id,
                "ENGINE_NOT_REGISTERED",
            )
            return request
        if not adapter.capability.is_available:
            self._unsupported(
                db,
                request,
                requested_level,
                readiness,
                actor_user_id,
                "ENGINE_UNAVAILABLE",
            )
            return request
        self._synchronize_engines(db)
        limitations = []
        if used_fallback:
            limitations.append(
                f"{requested_level.value} is unavailable; arithmetic fallback was executed"
            )
        self._decision(
            db,
            request,
            requested_level,
            selected_level,
            adapter.capability,
            readiness,
            SufficiencyStatus.NOT_EVALUATED,
            (
                EscalationStatus.NOT_SUPPORTED
                if used_fallback and requested_adapter is None
                else EscalationStatus.NOT_REQUIRED
            ),
            (
                OrchestrationDecisionType.EXECUTE_WITH_WARNINGS
                if limitations
                else OrchestrationDecisionType.EXECUTE
            ),
            "LOWEST_SUFFICIENT_ENGINE_SELECTED",
            "Selected the lowest implemented engine permitted by the definition and readiness",
        )
        self._step(
            db,
            request,
            OrchestrationStepType.ENGINE_SELECTION,
            OrchestrationStepStatus.COMPLETED,
            level=selected_level,
            engine=adapter.capability,
            limitations=limitations,
        )
        self._transition(
            db,
            request,
            OrchestrationStatus.EXECUTING,
            "engine_selected",
            actor_user_id,
        )
        execution = adapter.execute(
            db,
            organization_id,
            payload,
            actor_user_id,
            f"orchestration:{request.id}",
        )
        if execution.organization_id != organization_id:
            raise OrchestrationError(
                "CROSS_TENANT_REFERENCE",
                "Execution is not eligible",
                http_status=404,
            )
        if execution.status == IntelligenceExecutionStatus.BLOCKED.value:
            self._step(
                db,
                request,
                OrchestrationStepType.EXECUTION,
                OrchestrationStepStatus.BLOCKED,
                level=selected_level,
                engine=adapter.capability,
                execution=execution,
                block_reason="EXECUTION_BLOCKED",
                limitations=[execution.non_execution_reason or "Execution blocked"],
            )
            self._transition(
                db,
                request,
                OrchestrationStatus.BLOCKED,
                "EXECUTION_BLOCKED",
                actor_user_id,
            )
            request.completed_at = datetime.now(UTC)
            db.commit()
            db.refresh(request)
            return request
        if execution.status == IntelligenceExecutionStatus.FAILED.value:
            self._step(
                db,
                request,
                OrchestrationStepType.EXECUTION,
                OrchestrationStepStatus.FAILED,
                level=selected_level,
                engine=adapter.capability,
                execution=execution,
                error_code="EXECUTION_FAILED",
            )
            self._transition(
                db,
                request,
                OrchestrationStatus.FAILED,
                "EXECUTION_FAILED",
                actor_user_id,
            )
            request.completed_at = datetime.now(UTC)
            db.commit()
            db.refresh(request)
            return request
        self._step(
            db,
            request,
            OrchestrationStepType.EXECUTION,
            OrchestrationStepStatus.COMPLETED,
            level=selected_level,
            engine=adapter.capability,
            execution=execution,
        )
        sufficiency = self.sufficiency.evaluate(execution, used_fallback=used_fallback)
        escalation = self.escalation.evaluate(
            sufficiency,
            requested_level=requested_level,
            selected_level=selected_level,
            requested_engine_available=requested_adapter is not None,
        )
        self._step(
            db,
            request,
            OrchestrationStepType.SUFFICIENCY_EVALUATION,
            OrchestrationStepStatus.COMPLETED,
            level=selected_level,
            output_summary={"sufficiency": sufficiency.value},
            limitations=limitations,
        )
        self._step(
            db,
            request,
            OrchestrationStepType.ESCALATION_EVALUATION,
            OrchestrationStepStatus.COMPLETED,
            level=selected_level,
            output_summary={"escalation": escalation.value},
            limitations=limitations,
        )
        self._decision(
            db,
            request,
            requested_level,
            selected_level,
            adapter.capability,
            readiness,
            sufficiency,
            escalation,
            OrchestrationDecisionType.STOP_WITH_CURRENT_RESULT,
            "CURRENT_RESULT_EVALUATED",
            "The deterministic sufficiency and escalation policies evaluated the result",
        )
        publication_failed = False
        if payload.publish_finding and payload.finding_candidate is not None:
            candidate = payload.finding_candidate.model_copy(
                update={"execution_id": execution.id, "result_id": execution.id}
            )
            try:
                finding = finding_publication_service.publish_candidate_finding(
                    db, organization_id, candidate, actor_user_id
                )
            except FindingPlatformError as exc:
                publication_failed = True
                request.limitations = [
                    *limitations,
                    f"Finding publication failed: {exc.code}",
                ]
                self._step(
                    db,
                    request,
                    OrchestrationStepType.FINDING_PUBLICATION,
                    OrchestrationStepStatus.FAILED,
                    level=selected_level,
                    execution=execution,
                    error_code="FINDING_PUBLICATION_FAILED",
                )
            else:
                self._step(
                    db,
                    request,
                    OrchestrationStepType.FINDING_PUBLICATION,
                    OrchestrationStepStatus.COMPLETED,
                    level=selected_level,
                    execution=execution,
                    finding_id=finding.id,
                    output_summary={"finding_id": str(finding.id)},
                )
        target = (
            OrchestrationStatus.PARTIALLY_COMPLETED
            if publication_failed
            else (
                OrchestrationStatus.COMPLETED_WITH_LIMITATIONS
                if sufficiency == SufficiencyStatus.SUFFICIENT_WITH_LIMITATIONS
                else OrchestrationStatus.COMPLETED
            )
        )
        request.warnings = list(execution.warnings)
        request.limitations = request.limitations or limitations
        request.completed_at = datetime.now(UTC)
        self._transition(db, request, target, "orchestration_finalized", actor_user_id)
        self._step(
            db,
            request,
            OrchestrationStepType.COMPLETION,
            OrchestrationStepStatus.COMPLETED,
            level=selected_level,
            execution=execution,
            output_summary={"outcome": target.value},
            limitations=request.limitations,
        )
        db.commit()
        db.refresh(request)
        return request

    def get(
        self, db: Session, organization_id: UUID, orchestration_id: UUID
    ) -> IntelligenceOrchestrationRequest:
        request = db.scalar(
            select(IntelligenceOrchestrationRequest).where(
                IntelligenceOrchestrationRequest.id == orchestration_id,
                IntelligenceOrchestrationRequest.organization_id == organization_id,
            )
        )
        if request is None:
            raise OrchestrationError(
                "ORCHESTRATION_NOT_FOUND",
                "Orchestration not found",
                http_status=404,
            )
        return request

    def list_requests(
        self,
        db: Session,
        organization_id: UUID,
        *,
        page: int,
        page_size: int,
        status: str | None = None,
        analytical_level: str | None = None,
        definition_code: str | None = None,
        engine_code: str | None = None,
        requested_from: datetime | None = None,
        requested_to: datetime | None = None,
    ) -> tuple[list[IntelligenceOrchestrationRequest], int]:
        filters: list[Any] = [IntelligenceOrchestrationRequest.organization_id == organization_id]
        if status:
            filters.append(IntelligenceOrchestrationRequest.status == status)
        if analytical_level:
            filters.append(
                IntelligenceOrchestrationRequest.requested_analytical_level == analytical_level
            )
        if definition_code:
            filters.append(IntelligenceOrchestrationRequest.definition_code == definition_code)
        if requested_from:
            filters.append(IntelligenceOrchestrationRequest.requested_at >= requested_from)
        if requested_to:
            filters.append(IntelligenceOrchestrationRequest.requested_at <= requested_to)
        if engine_code:
            filters.append(
                IntelligenceOrchestrationRequest.id.in_(
                    select(IntelligenceOrchestrationDecision.orchestration_request_id).where(
                        IntelligenceOrchestrationDecision.organization_id == organization_id,
                        IntelligenceOrchestrationDecision.selected_engine_code == engine_code,
                    )
                )
            )
        total = (
            db.scalar(select(func.count(IntelligenceOrchestrationRequest.id)).where(*filters)) or 0
        )
        items = list(
            db.scalars(
                select(IntelligenceOrchestrationRequest)
                .where(*filters)
                .order_by(
                    IntelligenceOrchestrationRequest.requested_at.desc(),
                    IntelligenceOrchestrationRequest.id,
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        return items, total

    def decisions(
        self, db: Session, organization_id: UUID, orchestration_id: UUID
    ) -> list[IntelligenceOrchestrationDecision]:
        self.get(db, organization_id, orchestration_id)
        return list(
            db.scalars(
                select(IntelligenceOrchestrationDecision)
                .where(
                    IntelligenceOrchestrationDecision.organization_id == organization_id,
                    IntelligenceOrchestrationDecision.orchestration_request_id == orchestration_id,
                )
                .order_by(IntelligenceOrchestrationDecision.decision_sequence)
            ).all()
        )

    def steps(
        self, db: Session, organization_id: UUID, orchestration_id: UUID
    ) -> list[IntelligenceOrchestrationStep]:
        self.get(db, organization_id, orchestration_id)
        return list(
            db.scalars(
                select(IntelligenceOrchestrationStep)
                .where(
                    IntelligenceOrchestrationStep.organization_id == organization_id,
                    IntelligenceOrchestrationStep.orchestration_request_id == orchestration_id,
                )
                .order_by(IntelligenceOrchestrationStep.step_sequence)
            ).all()
        )

    def history(
        self, db: Session, organization_id: UUID, orchestration_id: UUID
    ) -> list[IntelligenceOrchestrationStatusHistory]:
        self.get(db, organization_id, orchestration_id)
        return list(
            db.scalars(
                select(IntelligenceOrchestrationStatusHistory)
                .where(
                    IntelligenceOrchestrationStatusHistory.organization_id == organization_id,
                    IntelligenceOrchestrationStatusHistory.orchestration_request_id
                    == orchestration_id,
                )
                .order_by(IntelligenceOrchestrationStatusHistory.transition_sequence)
            ).all()
        )

    def engines_list(self, db: Session) -> list[IntelligenceEngineRegistration]:
        self._synchronize_engines(db)
        db.commit()
        return list(
            db.scalars(
                select(IntelligenceEngineRegistration).order_by(
                    IntelligenceEngineRegistration.engine_code,
                    IntelligenceEngineRegistration.engine_version,
                )
            ).all()
        )

    def engine(self, db: Session, engine_code: str) -> IntelligenceEngineRegistration:
        self._synchronize_engines(db)
        db.commit()
        registration = db.scalar(
            select(IntelligenceEngineRegistration).where(
                IntelligenceEngineRegistration.engine_code == engine_code
            )
        )
        if registration is None:
            raise OrchestrationError(
                "ENGINE_NOT_REGISTERED",
                "Engine not registered",
                http_status=404,
            )
        return registration

    def _validate_references(
        self, db: Session, organization_id: UUID, payload: OrchestrationCreate
    ) -> None:
        organization = db.scalar(
            select(Organization).where(
                Organization.id == organization_id,
                Organization.status == OrganizationStatus.ACTIVE.value,
            )
        )
        if organization is None:
            raise OrchestrationError(
                "CROSS_TENANT_REFERENCE", "Organization is not eligible", http_status=404
            )
        dataset = db.scalar(
            select(Dataset).where(
                Dataset.id == payload.dataset_id,
                Dataset.organization_id == organization_id,
            )
        )
        if dataset is None:
            raise OrchestrationError(
                "CROSS_TENANT_REFERENCE", "Dataset is not eligible", http_status=404
            )
        if payload.dataset_version_id is not None:
            version = db.scalar(
                select(DatasetVersion).where(
                    DatasetVersion.id == payload.dataset_version_id,
                    DatasetVersion.organization_id == organization_id,
                    DatasetVersion.dataset_id == payload.dataset_id,
                )
            )
            if version is None:
                raise OrchestrationError(
                    "CROSS_TENANT_REFERENCE",
                    "Dataset version is not eligible",
                    http_status=404,
                )
        self._assessment(db, organization_id, payload)
        readiness = db.scalar(
            select(AnalyticalReadinessDecision).where(
                AnalyticalReadinessDecision.id == payload.analytical_readiness_id,
                AnalyticalReadinessDecision.organization_id == organization_id,
                AnalyticalReadinessDecision.trust_assessment_id == payload.trust_assessment_id,
            )
        )
        if readiness is None:
            raise OrchestrationError(
                "CROSS_TENANT_REFERENCE",
                "Readiness decision is not eligible",
                http_status=404,
            )

    @staticmethod
    def _assessment(
        db: Session, organization_id: UUID, payload: OrchestrationCreate
    ) -> TrustAssessment:
        assessment = db.scalar(
            select(TrustAssessment).where(
                TrustAssessment.id == payload.trust_assessment_id,
                TrustAssessment.organization_id == organization_id,
                TrustAssessment.dataset_id == payload.dataset_id,
            )
        )
        if assessment is None:
            raise OrchestrationError(
                "CROSS_TENANT_REFERENCE",
                "Trust assessment is not eligible",
                http_status=404,
            )
        if assessment.status not in {
            TrustAssessmentStatus.COMPLETED.value,
            TrustAssessmentStatus.COMPLETED_WITH_WARNINGS.value,
        }:
            raise OrchestrationError(
                "TRUST_REQUIREMENT_NOT_MET",
                "Trust assessment is not complete",
            )
        return assessment

    @staticmethod
    def _readiness_level(level: OrchestrationAnalyticalLevel) -> str | None:
        mapping = {
            OrchestrationAnalyticalLevel.ARITHMETIC: "arithmetic",
            OrchestrationAnalyticalLevel.RULE_BASED: "arithmetic",
            OrchestrationAnalyticalLevel.STATISTICAL: "statistical",
            OrchestrationAnalyticalLevel.PREDICTIVE: "predictive",
            OrchestrationAnalyticalLevel.OPTIMIZATION: "optimization",
            OrchestrationAnalyticalLevel.RECOVERY: "economic_recovery",
        }
        return mapping.get(level)

    def _readiness(
        self,
        db: Session,
        organization_id: UUID,
        payload: OrchestrationCreate,
        definition_level: OrchestrationAnalyticalLevel,
    ) -> AnalyticalReadinessDecision:
        expected_level = self._readiness_level(
            payload.requested_analytical_level or definition_level
        )
        readiness = db.scalar(
            select(AnalyticalReadinessDecision).where(
                AnalyticalReadinessDecision.id == payload.analytical_readiness_id,
                AnalyticalReadinessDecision.organization_id == organization_id,
                AnalyticalReadinessDecision.trust_assessment_id == payload.trust_assessment_id,
            )
        )
        if readiness is None:
            raise OrchestrationError(
                "CROSS_TENANT_REFERENCE",
                "Readiness decision is not eligible",
                http_status=404,
            )
        if expected_level is None or readiness.analytical_level != expected_level:
            raise OrchestrationError(
                "READINESS_REQUIREMENT_NOT_MET",
                "Readiness decision does not cover the requested analytical level",
            )
        return readiness

    def _unsupported(
        self,
        db: Session,
        request: IntelligenceOrchestrationRequest,
        requested_level: OrchestrationAnalyticalLevel,
        readiness: AnalyticalReadinessDecision,
        actor_user_id: UUID,
        reason: str,
    ) -> None:
        self._decision(
            db,
            request,
            requested_level,
            None,
            None,
            readiness,
            SufficiencyStatus.NOT_EVALUATED,
            EscalationStatus.NOT_SUPPORTED,
            OrchestrationDecisionType.UNSUPPORTED,
            reason,
            "No eligible implemented engine can satisfy the governed request",
        )
        self._step(
            db,
            request,
            OrchestrationStepType.ENGINE_SELECTION,
            OrchestrationStepStatus.BLOCKED,
            level=requested_level,
            block_reason=reason,
        )
        self._transition(db, request, OrchestrationStatus.UNSUPPORTED, reason, actor_user_id)
        request.completed_at = datetime.now(UTC)
        db.commit()
        db.refresh(request)

    def _synchronize_engines(self, db: Session) -> None:
        for adapter in self.engines.list():
            capability = adapter.capability
            row = db.scalar(
                select(IntelligenceEngineRegistration).where(
                    IntelligenceEngineRegistration.engine_code == capability.engine_code,
                    IntelligenceEngineRegistration.engine_version == capability.engine_version,
                )
            )
            values = {
                "engine_name": capability.engine_name,
                "analytical_level": capability.analytical_level.value,
                "capability_code": capability.capability_code,
                "status": (
                    EngineRegistrationStatus.ACTIVE.value
                    if capability.is_available
                    else EngineRegistrationStatus.UNAVAILABLE.value
                ),
                "is_available": capability.is_available,
                "supports_sync": capability.supports_sync,
                "supports_async": capability.supports_async,
                "input_contract_version": capability.input_contract_version,
                "output_contract_version": capability.output_contract_version,
                "implementation_reference": capability.implementation_reference,
            }
            if row is None:
                db.add(
                    IntelligenceEngineRegistration(
                        engine_code=capability.engine_code,
                        engine_version=capability.engine_version,
                        **values,
                    )
                )
            else:
                for key, value in values.items():
                    setattr(row, key, value)
        db.flush()

    @staticmethod
    def _context_fingerprint(organization_id: UUID, payload: OrchestrationCreate) -> str:
        return _hash(
            {
                "organization_id": organization_id,
                "definition_code": payload.definition_code,
                "definition_version": payload.definition_version,
                "dataset_id": payload.dataset_id,
                "dataset_version_id": payload.dataset_version_id,
                "dataset_reference": payload.dataset_reference,
                "trust_assessment_id": payload.trust_assessment_id,
                "readiness_id": payload.analytical_readiness_id,
                "requested_level": payload.requested_analytical_level,
                "execution_type": payload.execution_type,
                "parameters": payload.parameters,
                "record_count": len(payload.records),
                "evidence_references": [
                    {
                        "raw": item.raw_record_reference_id,
                        "lineage": item.lineage_node_id,
                        "canonical": item.canonical_record_identifier,
                        "aggregate": item.aggregate_reference,
                    }
                    for item in payload.evidence
                ],
                "publish_finding": payload.publish_finding,
                "finding_fingerprint": (
                    _hash(payload.finding_candidate.model_dump())
                    if payload.finding_candidate
                    else None
                ),
            }
        )

    @staticmethod
    def _bounded_context(value: dict[str, object]) -> dict[str, object]:
        encoded = json.dumps(value, default=str)
        if len(encoded) > 8000:
            raise OrchestrationError(
                "INVALID_IDEMPOTENCY_KEY", "Request context exceeds the bounded size"
            )
        decoded: object = json.loads(encoded)
        if not isinstance(decoded, dict):
            raise OrchestrationError("INVALID_IDEMPOTENCY_KEY", "Request context must be an object")
        return decoded

    def _transition(
        self,
        db: Session,
        request: IntelligenceOrchestrationRequest,
        target: OrchestrationStatus,
        reason: str,
        actor_user_id: UUID,
    ) -> None:
        previous = request.status
        if target.value not in self.transitions.get(previous, set()):
            raise OrchestrationError(
                "INVALID_STATUS_TRANSITION",
                "Invalid orchestration status transition",
                http_status=409,
            )
        request.status = target.value
        request.updated_at = datetime.now(UTC)
        self._history(db, request, previous, target, reason, actor_user_id)

    def _history(
        self,
        db: Session,
        request: IntelligenceOrchestrationRequest,
        previous: str | None,
        target: OrchestrationStatus,
        reason: str,
        actor_user_id: UUID | None = None,
    ) -> None:
        transition_sequence = (
            db.scalar(
                select(func.max(IntelligenceOrchestrationStatusHistory.transition_sequence)).where(
                    IntelligenceOrchestrationStatusHistory.orchestration_request_id == request.id
                )
            )
            or 0
        ) + 1
        db.add(
            IntelligenceOrchestrationStatusHistory(
                organization_id=request.organization_id,
                orchestration_request_id=request.id,
                transition_sequence=transition_sequence,
                previous_status=previous,
                new_status=target.value,
                reason_code=reason,
                changed_by_user_id=actor_user_id or request.requested_by_user_id,
                changed_at=datetime.now(UTC),
                metadata_json={},
            )
        )

    @staticmethod
    def _next_step(db: Session, request_id: UUID) -> int:
        return (
            db.scalar(
                select(func.max(IntelligenceOrchestrationStep.step_sequence)).where(
                    IntelligenceOrchestrationStep.orchestration_request_id == request_id
                )
            )
            or 0
        ) + 1

    def _step(
        self,
        db: Session,
        request: IntelligenceOrchestrationRequest,
        step_type: OrchestrationStepType,
        status: OrchestrationStepStatus,
        *,
        level: OrchestrationAnalyticalLevel | None = None,
        engine: EngineCapability | None = None,
        execution: IntelligenceExecution | None = None,
        finding_id: UUID | None = None,
        input_summary: dict[str, object] | None = None,
        output_summary: dict[str, object] | None = None,
        warnings: list[str] | None = None,
        limitations: list[str] | None = None,
        block_reason: str | None = None,
        error_code: str | None = None,
    ) -> None:
        sequence = self._next_step(db, request.id)
        content = {
            "request_id": request.id,
            "sequence": sequence,
            "type": step_type,
            "status": status,
            "level": level,
            "engine": engine.engine_code if engine else None,
            "execution": execution.id if execution else None,
            "finding": finding_id,
            "input": input_summary or {},
            "output": output_summary or {},
            "warnings": warnings or [],
            "limitations": limitations or [],
            "block_reason": block_reason,
            "error_code": error_code,
        }
        db.add(
            IntelligenceOrchestrationStep(
                organization_id=request.organization_id,
                orchestration_request_id=request.id,
                step_sequence=sequence,
                analytical_level=level.value if level else None,
                engine_code=engine.engine_code if engine else None,
                engine_version=engine.engine_version if engine else None,
                step_type=step_type.value,
                status=status.value,
                started_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
                source_execution_id=execution.id if execution else None,
                source_result_id=(
                    execution.id
                    if execution and execution.status == IntelligenceExecutionStatus.COMPLETED.value
                    else None
                ),
                finding_id=finding_id,
                input_reference_summary=input_summary or {},
                output_reference_summary=output_summary or {},
                warnings=warnings or [],
                limitations=limitations or [],
                block_reason_code=block_reason,
                error_code=error_code,
                content_hash=_hash(content),
            )
        )
        db.flush()

    @staticmethod
    def _next_decision(db: Session, request_id: UUID) -> int:
        return (
            db.scalar(
                select(func.max(IntelligenceOrchestrationDecision.decision_sequence)).where(
                    IntelligenceOrchestrationDecision.orchestration_request_id == request_id
                )
            )
            or 0
        ) + 1

    def _decision(
        self,
        db: Session,
        request: IntelligenceOrchestrationRequest,
        requested_level: OrchestrationAnalyticalLevel,
        selected_level: OrchestrationAnalyticalLevel | None,
        engine: EngineCapability | None,
        readiness: AnalyticalReadinessDecision,
        sufficiency: SufficiencyStatus,
        escalation: EscalationStatus,
        decision: OrchestrationDecisionType,
        reason: str,
        summary: str,
    ) -> None:
        sequence = self._next_decision(db, request.id)
        content = {
            "request_id": request.id,
            "sequence": sequence,
            "definition": (request.definition_code, request.definition_version),
            "requested": requested_level,
            "selected": selected_level,
            "engine": engine.engine_code if engine else None,
            "trust": request.trust_assessment_id,
            "readiness": (readiness.id, readiness.readiness_status),
            "sufficiency": sufficiency,
            "escalation": escalation,
            "decision": decision,
            "reason": reason,
            "policy": (POLICY_CODE, POLICY_VERSION),
        }
        db.add(
            IntelligenceOrchestrationDecision(
                organization_id=request.organization_id,
                orchestration_request_id=request.id,
                decision_sequence=sequence,
                definition_code=request.definition_code,
                definition_version=request.definition_version,
                requested_level=requested_level.value,
                selected_level=selected_level.value if selected_level else None,
                selected_engine_code=engine.engine_code if engine else None,
                selected_engine_version=engine.engine_version if engine else None,
                alternatives_considered=[
                    {
                        "level": requested_level.value,
                        "availability": (
                            "executable_now"
                            if self.engines.for_level(requested_level)
                            else "deferred_to_later_work_package"
                        ),
                    }
                ],
                trust_status="satisfied",
                readiness_status=readiness.readiness_status,
                sufficiency_status=sufficiency.value,
                escalation_status=escalation.value,
                decision=decision.value,
                decision_reason_code=reason,
                decision_summary=summary,
                policy_code=POLICY_CODE,
                policy_version=POLICY_VERSION,
                content_hash=_hash(content),
                decided_at=datetime.now(UTC),
            )
        )
        db.flush()


orchestration_service = OrchestrationService()
