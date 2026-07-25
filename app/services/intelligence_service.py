from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.engines.arithmetic_engine import ArithmeticEvaluationError, ArithmeticEvaluator
from app.engines.rule_engine import RuleEvaluator
from app.models.ingestion import Dataset, DatasetVersion
from app.models.intelligence import (
    IntelligenceExecution,
    IntelligenceExecutionEvidence,
    IntelligenceExecutionStatus,
)
from app.models.raw_lineage import LineageNode, RawRecordReference
from app.models.trust import (
    AnalyticalLevel,
    AnalyticalReadinessDecision,
    ReadinessStatus,
    TrustAssessment,
    TrustAssessmentStatus,
)
from app.registries.calculation_registry import (
    CalculationRegistry,
    default_calculation_registry,
)
from app.registries.rule_registry import RuleRegistry, default_rule_registry
from app.schemas.intelligence import ExecutionType, IntelligenceExecutionCreate


class IntelligenceNotFoundError(ValueError):
    pass


class IntelligenceConflictError(ValueError):
    pass


class IntelligenceInputError(ValueError):
    pass


class IntelligenceExecutionService:
    def __init__(
        self,
        calculations: CalculationRegistry | None = None,
        rules: RuleRegistry | None = None,
        arithmetic: ArithmeticEvaluator | None = None,
        rule_evaluator: RuleEvaluator | None = None,
    ) -> None:
        self.calculations = calculations or default_calculation_registry()
        self.rules = rules or default_rule_registry()
        self.arithmetic = arithmetic or ArithmeticEvaluator()
        self.rule_evaluator = rule_evaluator or RuleEvaluator()

    def execute(
        self,
        db: Session,
        organization_id: UUID,
        payload: IntelligenceExecutionCreate,
        actor_user_id: UUID,
    ) -> IntelligenceExecution:
        dataset = self._dataset(db, organization_id, payload.dataset_id)
        self._validate_dataset_version(db, organization_id, dataset.id, payload.dataset_version_id)
        if payload.idempotency_key is not None:
            existing = db.scalar(
                select(IntelligenceExecution).where(
                    IntelligenceExecution.organization_id == organization_id,
                    IntelligenceExecution.idempotency_key == payload.idempotency_key,
                )
            )
            if existing is not None:
                return existing
        assessment, readiness = self._readiness(
            db, organization_id, dataset.id, payload.trust_assessment_id
        )
        evaluation_time = payload.evaluation_time or datetime.now(UTC)
        if payload.execution_type == ExecutionType.CALCULATION:
            calculation_definition = self.calculations.get(
                payload.definition_code, payload.definition_version
            )
            definition_data = asdict(calculation_definition)
        else:
            rule_definition = self.rules.get(payload.definition_code, payload.definition_version)
            definition_data = asdict(rule_definition)
        execution = IntelligenceExecution(
            organization_id=organization_id,
            dataset_id=dataset.id,
            dataset_version_id=payload.dataset_version_id,
            trust_assessment_id=assessment.id,
            readiness_decision_id=readiness.id,
            execution_type=payload.execution_type.value,
            definition_code=payload.definition_code,
            definition_version=payload.definition_version,
            definition_fingerprint=self._fingerprint(definition_data),
            input_fingerprint=self._fingerprint(
                {"records": payload.records, "parameters": payload.parameters}
            ),
            status=IntelligenceExecutionStatus.BLOCKED.value,
            idempotency_key=payload.idempotency_key,
            parameters_json=self._json_safe(payload.parameters),
            unit=payload.unit or definition_data.get("output_unit"),
            currency=payload.currency,
            exposure_value=payload.exposure_value,
            exposure_currency=payload.exposure_currency,
            blocking_rule_codes=list(readiness.blocking_rule_codes),
            warning_rule_codes=list(readiness.warning_rule_codes),
            warnings=[],
            limitations=[
                "Canonical records are supplied by a governed caller and are not persisted"
            ],
            input_period_start=payload.input_period_start,
            input_period_end=payload.input_period_end,
            evaluation_time=evaluation_time,
            created_by_user_id=actor_user_id,
        )
        db.add(execution)
        db.flush()
        if readiness.readiness_status not in {
            ReadinessStatus.READY.value,
            ReadinessStatus.READY_WITH_WARNINGS.value,
        }:
            execution.non_execution_reason = readiness.explanation
            execution.completed_at = datetime.now(UTC)
            db.commit()
            db.refresh(execution)
            return execution
        try:
            if payload.execution_type == ExecutionType.CALCULATION:
                outcome = self.arithmetic.execute(
                    calculation_definition, payload.records, payload.parameters
                )
                execution.result_value = outcome.value
                execution.checked_record_count = outcome.checked_count
                execution.excluded_record_count = outcome.excluded_count
            else:
                rule_outcome = self.rule_evaluator.execute(rule_definition, payload.parameters)
                execution.result_value = rule_outcome.value
                execution.comparison_value = rule_outcome.comparison_value
                execution.threshold_value = rule_outcome.threshold_value
                execution.breached = rule_outcome.breached
                execution.checked_record_count = 1
                execution.affected_record_count = int(rule_outcome.breached)
        except ArithmeticEvaluationError as exc:
            execution.status = IntelligenceExecutionStatus.FAILED.value
            execution.non_execution_reason = str(exc)
        else:
            execution.status = IntelligenceExecutionStatus.COMPLETED.value
        self._add_evidence(db, organization_id, execution.id, payload)
        execution.completed_at = datetime.now(UTC)
        db.commit()
        db.refresh(execution)
        return execution

    def get(self, db: Session, organization_id: UUID, execution_id: UUID) -> IntelligenceExecution:
        execution = db.scalar(
            select(IntelligenceExecution).where(
                IntelligenceExecution.id == execution_id,
                IntelligenceExecution.organization_id == organization_id,
            )
        )
        if execution is None:
            raise IntelligenceNotFoundError("Intelligence execution not found")
        return execution

    def list(
        self, db: Session, organization_id: UUID, *, offset: int = 0, limit: int = 100
    ) -> list[IntelligenceExecution]:
        return list(
            db.scalars(
                select(IntelligenceExecution)
                .where(IntelligenceExecution.organization_id == organization_id)
                .order_by(IntelligenceExecution.created_at.desc(), IntelligenceExecution.id)
                .offset(offset)
                .limit(limit)
            ).all()
        )

    def _dataset(self, db: Session, organization_id: UUID, dataset_id: UUID) -> Dataset:
        dataset = db.scalar(
            select(Dataset).where(
                Dataset.id == dataset_id, Dataset.organization_id == organization_id
            )
        )
        if dataset is None:
            raise IntelligenceNotFoundError("Dataset not found")
        return dataset

    def _validate_dataset_version(
        self,
        db: Session,
        organization_id: UUID,
        dataset_id: UUID,
        version_id: UUID | None,
    ) -> None:
        if version_id is None:
            return
        version = db.scalar(
            select(DatasetVersion).where(
                DatasetVersion.id == version_id,
                DatasetVersion.organization_id == organization_id,
                DatasetVersion.dataset_id == dataset_id,
            )
        )
        if version is None:
            raise IntelligenceNotFoundError("Dataset version not found")

    def _readiness(
        self,
        db: Session,
        organization_id: UUID,
        dataset_id: UUID,
        assessment_id: UUID | None,
    ) -> tuple[TrustAssessment, AnalyticalReadinessDecision]:
        query = select(TrustAssessment).where(
            TrustAssessment.organization_id == organization_id,
            TrustAssessment.dataset_id == dataset_id,
            TrustAssessment.status.in_(
                (
                    TrustAssessmentStatus.COMPLETED.value,
                    TrustAssessmentStatus.COMPLETED_WITH_WARNINGS.value,
                )
            ),
        )
        if assessment_id is not None:
            query = query.where(TrustAssessment.id == assessment_id)
        assessment = db.scalar(
            query.order_by(TrustAssessment.completed_at.desc(), TrustAssessment.id).limit(1)
        )
        if assessment is None:
            raise IntelligenceNotFoundError("Completed trust assessment not found")
        readiness = db.scalar(
            select(AnalyticalReadinessDecision).where(
                AnalyticalReadinessDecision.organization_id == organization_id,
                AnalyticalReadinessDecision.trust_assessment_id == assessment.id,
                AnalyticalReadinessDecision.analytical_level == AnalyticalLevel.ARITHMETIC.value,
            )
        )
        if readiness is None:
            raise IntelligenceNotFoundError("Arithmetic readiness decision not found")
        return assessment, readiness

    def _add_evidence(
        self,
        db: Session,
        organization_id: UUID,
        execution_id: UUID,
        payload: IntelligenceExecutionCreate,
    ) -> None:
        for reference in payload.evidence:
            if reference.raw_record_reference_id is not None:
                raw = db.scalar(
                    select(RawRecordReference).where(
                        RawRecordReference.id == reference.raw_record_reference_id,
                        RawRecordReference.organization_id == organization_id,
                    )
                )
                if raw is None:
                    raise IntelligenceNotFoundError("Raw record reference not found")
            if reference.lineage_node_id is not None:
                node = db.scalar(
                    select(LineageNode).where(
                        LineageNode.id == reference.lineage_node_id,
                        LineageNode.organization_id == organization_id,
                    )
                )
                if node is None:
                    raise IntelligenceNotFoundError("Lineage node not found")
            db.add(
                IntelligenceExecutionEvidence(
                    organization_id=organization_id,
                    execution_id=execution_id,
                    **reference.model_dump(),
                )
            )

    @staticmethod
    def _json_safe(value: dict[str, object]) -> dict[str, object]:
        converted: object = json.loads(json.dumps(value, default=str))
        if not isinstance(converted, dict):
            raise IntelligenceInputError("Parameters must be an object")
        return converted

    @staticmethod
    def _fingerprint(value: object) -> str:
        serialized = json.dumps(value, default=str, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode()).hexdigest()


intelligence_execution_service = IntelligenceExecutionService()
