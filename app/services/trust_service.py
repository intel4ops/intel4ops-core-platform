from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.engines.trust_engine import (
    ProgressiveReadinessPolicy,
    TrustRule,
    TrustRuleOutcome,
    TrustRuleRegistry,
    calculate_scores,
    default_rule_registry,
)
from app.models.ingestion import Dataset, IngestionBatch
from app.models.trust import (
    AnalyticalReadinessDecision,
    TrustAssessment,
    TrustAssessmentStatus,
    TrustEvidence,
    TrustExecutionStatus,
    TrustResultStatus,
    TrustRuleResult,
)
from app.schemas.trust import TrustAssessmentCreate

MAX_TOTAL_EVIDENCE = 500


class TrustNotFoundError(ValueError):
    pass


class TrustTenantMismatchError(ValueError):
    pass


class TrustConfigurationError(ValueError):
    pass


class NoApplicableTrustRulesError(ValueError):
    pass


class TrustAssessmentService:
    def __init__(
        self,
        registry: TrustRuleRegistry | None = None,
        readiness_policy: ProgressiveReadinessPolicy | None = None,
    ) -> None:
        self.registry = registry or default_rule_registry()
        self.readiness_policy = readiness_policy or ProgressiveReadinessPolicy()

    def create_and_execute(
        self,
        db: Session,
        organization_id: UUID,
        dataset_id: UUID,
        payload: TrustAssessmentCreate,
    ) -> TrustAssessment:
        dataset = self._dataset(db, organization_id, dataset_id)
        if payload.ingestion_batch_id is not None:
            batch = db.scalar(
                select(IngestionBatch).where(
                    IngestionBatch.id == payload.ingestion_batch_id,
                    IngestionBatch.organization_id == organization_id,
                )
            )
            if batch is None:
                raise TrustTenantMismatchError("Ingestion batch not found in organization")
            if batch.source_system_id != dataset.source_system_id:
                raise TrustConfigurationError(
                    "Dataset and ingestion batch source systems do not match"
                )
        applicable = self.registry.applicable(dataset.dataset_type, payload.rule_configurations)
        if not applicable:
            raise NoApplicableTrustRulesError("No applicable trust rules")
        assessment = TrustAssessment(
            organization_id=organization_id,
            dataset_id=dataset.id,
            ingestion_batch_id=payload.ingestion_batch_id,
            industry_pack_code=payload.industry_pack_code,
            status=TrustAssessmentStatus.RUNNING.value,
            assessed_row_count=len(payload.records),
        )
        db.add(assessment)
        db.flush()
        evaluation_time = payload.evaluation_time or datetime.now(UTC)
        executed: list[tuple[TrustRule, TrustRuleOutcome]] = []
        execution_errored = False
        evidence_count = 0
        for rule, configuration in applicable:
            try:
                outcome = rule.execute(payload.records, configuration, evaluation_time)
                execution_status = TrustExecutionStatus.COMPLETED
            except (TypeError, ValueError, KeyError, ArithmeticError):
                execution_errored = True
                execution_status = TrustExecutionStatus.ERRORED
                outcome = TrustRuleOutcome(
                    status=TrustResultStatus.FAILED,
                    checked_count=len(payload.records),
                    affected_count=0,
                    score=0.0,
                    message="Rule execution failed",
                )
            executed.append((rule, outcome))
            result = self._persist_result(
                db,
                organization_id,
                assessment.id,
                rule,
                configuration,
                outcome,
                execution_status,
            )
            db.flush()
            for evidence in outcome.evidence:
                if evidence_count >= MAX_TOTAL_EVIDENCE:
                    break
                observed = (
                    {"value": evidence.observed_value}
                    if evidence.observed_value is not None
                    else None
                )
                db.add(
                    TrustEvidence(
                        organization_id=organization_id,
                        trust_rule_result_id=result.id,
                        dataset_id=dataset.id,
                        source_record_identifier=evidence.record_identifier,
                        field_name=evidence.field_name,
                        observed_value=observed,
                        expected_condition=evidence.expected_condition,
                        evidence_type=evidence.evidence_type,
                        source_reference=evidence.source_reference,
                    )
                )
                evidence_count += 1
        dimensions, overall = calculate_scores(executed)
        assessment.overall_score = overall
        for dimension, score in dimensions.items():
            field_name = f"{dimension.value}_score"
            if hasattr(assessment, field_name):
                setattr(assessment, field_name, score)
        counts = {
            status: sum(1 for _, outcome in executed if outcome.status == status)
            for status in TrustResultStatus
        }
        assessment.passed_rule_count = counts[TrustResultStatus.PASSED]
        assessment.warning_rule_count = counts[TrustResultStatus.WARNING]
        assessment.failed_rule_count = counts[TrustResultStatus.FAILED]
        assessment.skipped_rule_count = (
            counts[TrustResultStatus.SKIPPED] + counts[TrustResultStatus.NOT_APPLICABLE]
        )
        assessment.completed_at = datetime.now(UTC)
        if execution_errored:
            assessment.status = TrustAssessmentStatus.FAILED.value
        elif assessment.failed_rule_count:
            assessment.status = TrustAssessmentStatus.COMPLETED_WITH_WARNINGS.value
        else:
            assessment.status = TrustAssessmentStatus.COMPLETED.value
        for decision in self.readiness_policy.decide(len(payload.records), dimensions, executed):
            db.add(
                AnalyticalReadinessDecision(
                    organization_id=organization_id,
                    trust_assessment_id=assessment.id,
                    analytical_level=decision.level.value,
                    readiness_status=decision.status.value,
                    blocking_rule_codes=list(decision.blocking_codes),
                    warning_rule_codes=list(decision.warning_codes),
                    explanation=decision.explanation,
                )
            )
        db.commit()
        db.refresh(assessment)
        return assessment

    def _persist_result(
        self,
        db: Session,
        organization_id: UUID,
        assessment_id: UUID,
        rule: TrustRule,
        configuration: dict[str, object],
        outcome: TrustRuleOutcome,
        execution_status: TrustExecutionStatus,
    ) -> TrustRuleResult:
        percentage = (
            None
            if outcome.checked_count == 0
            else round(outcome.affected_count * 100 / outcome.checked_count, 2)
        )
        threshold = {
            **rule.threshold_definition,
            **{
                key: value
                for key, value in configuration.items()
                if key
                in {
                    "maximum_affected_percentage",
                    "minimum_date",
                    "maximum_date",
                    "minimum",
                    "maximum",
                    "maximum_age_days",
                }
            },
        }
        result = TrustRuleResult(
            organization_id=organization_id,
            trust_assessment_id=assessment_id,
            rule_code=rule.code,
            rule_version=rule.version,
            rule_name=rule.name,
            dimension=rule.dimension.value,
            severity=rule.severity.value,
            execution_status=execution_status.value,
            result_status=outcome.status.value,
            checked_record_count=outcome.checked_count,
            affected_record_count=outcome.affected_count,
            affected_percentage=percentage,
            threshold_definition=threshold,
            observed_value=outcome.observed_value,
            score=outcome.score,
            message=outcome.message,
            remediation_guidance=rule.remediation_guidance,
        )
        db.add(result)
        return result

    def _dataset(self, db: Session, organization_id: UUID, dataset_id: UUID) -> Dataset:
        dataset = db.scalar(
            select(Dataset).where(
                Dataset.id == dataset_id,
                Dataset.organization_id == organization_id,
            )
        )
        if dataset is None:
            raise TrustNotFoundError("Dataset not found")
        return dataset

    def get(self, db: Session, organization_id: UUID, assessment_id: UUID) -> TrustAssessment:
        assessment = db.scalar(
            select(TrustAssessment).where(
                TrustAssessment.id == assessment_id,
                TrustAssessment.organization_id == organization_id,
            )
        )
        if assessment is None:
            raise TrustNotFoundError("Trust assessment not found")
        return assessment

    def latest(self, db: Session, organization_id: UUID, dataset_id: UUID) -> TrustAssessment:
        self._dataset(db, organization_id, dataset_id)
        assessment = db.scalar(
            select(TrustAssessment)
            .where(
                TrustAssessment.organization_id == organization_id,
                TrustAssessment.dataset_id == dataset_id,
                TrustAssessment.status.in_(
                    (
                        TrustAssessmentStatus.COMPLETED.value,
                        TrustAssessmentStatus.COMPLETED_WITH_WARNINGS.value,
                    )
                ),
            )
            .order_by(TrustAssessment.completed_at.desc(), TrustAssessment.id)
            .limit(1)
        )
        if assessment is None:
            raise TrustNotFoundError("Completed trust assessment not found")
        return assessment

    def rule_results(
        self, db: Session, organization_id: UUID, assessment_id: UUID
    ) -> list[TrustRuleResult]:
        self.get(db, organization_id, assessment_id)
        return list(
            db.scalars(
                select(TrustRuleResult)
                .where(
                    TrustRuleResult.organization_id == organization_id,
                    TrustRuleResult.trust_assessment_id == assessment_id,
                )
                .order_by(TrustRuleResult.rule_code, TrustRuleResult.id)
            ).all()
        )

    def evidence(
        self,
        db: Session,
        organization_id: UUID,
        assessment_id: UUID,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[TrustEvidence], int]:
        self.get(db, organization_id, assessment_id)
        result_ids = select(TrustRuleResult.id).where(
            TrustRuleResult.organization_id == organization_id,
            TrustRuleResult.trust_assessment_id == assessment_id,
        )
        filters = (
            TrustEvidence.organization_id == organization_id,
            TrustEvidence.trust_rule_result_id.in_(result_ids),
        )
        total = db.scalar(select(func.count()).select_from(TrustEvidence).where(*filters)) or 0
        items = list(
            db.scalars(
                select(TrustEvidence)
                .where(*filters)
                .order_by(TrustEvidence.created_at, TrustEvidence.id)
                .offset(offset)
                .limit(limit)
            ).all()
        )
        return items, total

    def readiness(
        self, db: Session, organization_id: UUID, assessment_id: UUID
    ) -> list[AnalyticalReadinessDecision]:
        self.get(db, organization_id, assessment_id)
        return list(
            db.scalars(
                select(AnalyticalReadinessDecision)
                .where(
                    AnalyticalReadinessDecision.organization_id == organization_id,
                    AnalyticalReadinessDecision.trust_assessment_id == assessment_id,
                )
                .order_by(AnalyticalReadinessDecision.analytical_level)
            ).all()
        )


trust_assessment_service = TrustAssessmentService()
