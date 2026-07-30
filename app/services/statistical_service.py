from __future__ import annotations

import hashlib
import json
import math
import statistics
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.engines.statistical_engine import (
    InsufficientStatisticalDataError,
    StatisticalMethodError,
    StatisticalMethodMetadata,
    StatisticalMethodRegistry,
    StatisticalMethodResult,
    UnsupportedStatisticalMethodError,
    default_statistical_method_registry,
    finite_values,
    integer_parameter,
    median_absolute_deviation,
    numeric_parameter,
    percentile,
)
from app.models.statistics import (
    AnomalyDirection,
    AnomalyReviewFeedback,
    AnomalySeverity,
    AnomalySuppressionRecord,
    StatisticalBaseline,
    StatisticalExecution,
    StatisticalExecutionStatus,
    StatisticalExecutionStep,
    StatisticalMethodRegistration,
    StatisticalObservation,
    StatisticalScoreComponent,
)
from app.models.trust import (
    AnalyticalLevel,
    AnalyticalReadinessDecision,
    ReadinessStatus,
    TrustAssessment,
    TrustAssessmentStatus,
)
from app.schemas.oikb import ResolveRequest
from app.schemas.statistics import (
    ObservationReviewCreate,
    ObservationSuppressionCreate,
    PeriodStatus,
    StatisticalEvaluateRequest,
    StatisticalEvaluationRead,
    StatisticalExecutionCreate,
    StatisticalMethodRead,
)
from app.services.governed_provenance_service import (
    GovernedDatasetProvenance,
    GovernedProvenanceError,
    governed_dataset_provenance_service,
)
from app.services.oikb_service import (
    execution_package_export_service,
    knowledge_resolution_service,
)

ENGINE_VERSION = "1.0"
MAX_MISSING_PERCENTAGE_DEFAULT = 10.0


class StatisticalServiceError(ValueError):
    def __init__(self, code: str, message: str, *, http_status: int = 422) -> None:
        self.code = code
        self.http_status = http_status
        super().__init__(message)


@dataclass(frozen=True)
class ScoreComponent:
    code: str
    raw_value: float
    normalized_value: float
    weight: float
    contribution: float
    explanation: str


@dataclass(frozen=True)
class AnomalyScore:
    statistical_score: float
    confidence_score: float
    materiality_score: float
    severity: AnomalySeverity
    components: tuple[ScoreComponent, ...]


def _hash(value: object) -> str:
    encoded = json.dumps(value, default=str, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def _bounded(value: float) -> float:
    if not math.isfinite(value):
        return 0.0
    return round(max(0.0, min(1.0, value)), 5)


class BaselineService:
    def build(
        self,
        execution: StatisticalExecution,
        values: list[float],
        payload: StatisticalExecutionCreate,
        baseline_type: str,
    ) -> StatisticalBaseline:
        timestamps = [item.timestamp for item in payload.observations if item.timestamp is not None]
        entities = {
            item.entity_reference
            for item in payload.observations
            if item.entity_reference is not None
        }
        variance = statistics.variance(values) if len(values) > 1 else 0.0
        baseline_contract = {
            "baseline_type": baseline_type,
            "dataset_fingerprint": execution.dataset_fingerprint,
            "values_fingerprint": _hash(values),
            "time_window": [
                min(timestamps) if timestamps else None,
                max(timestamps) if timestamps else None,
            ],
            "record_count": len(values),
        }
        return StatisticalBaseline(
            organization_id=execution.organization_id,
            statistical_execution_id=execution.id,
            baseline_type=baseline_type,
            baseline_scope={
                "organization_id": str(execution.organization_id),
                "aggregate_only": baseline_type == "peer_group",
            },
            population_definition={
                "inclusion": "finite governed observations",
                "exclusion": "null and governed excluded events",
                "aggregation_grain": "request observation",
            },
            time_window_start=min(timestamps) if timestamps else None,
            time_window_end=max(timestamps) if timestamps else None,
            record_count=len(values),
            entity_count=len(entities),
            mean_value=statistics.mean(values),
            median_value=statistics.median(values),
            minimum_value=min(values),
            maximum_value=max(values),
            variance_value=variance,
            standard_deviation_value=math.sqrt(variance),
            mad_value=median_absolute_deviation(values),
            percentile_values={
                "p25": percentile(values, 0.25),
                "p50": percentile(values, 0.50),
                "p75": percentile(values, 0.75),
                "p95": percentile(values, 0.95),
            },
            baseline_fingerprint=_hash(baseline_contract),
            limitations=[
                "Baseline contains aggregate summaries only",
                "No cross-tenant raw observations are retained",
            ],
        )


class AnomalyScoringService:
    def score(
        self,
        result: StatisticalMethodResult,
        materiality: float,
        sample_size: int,
        parameters: dict[str, object],
    ) -> AnomalyScore:
        normalized = abs(result.normalized_deviation or 0.0)
        deviation_score = _bounded(normalized / max(float(result.threshold or 1.0), 1e-12))
        confidence = _bounded(
            min(
                1.0,
                sample_size / max(integer_parameter(parameters, "confidence_sample_size", 30), 1),
            )
            * (1.0 if result.is_anomaly else 0.8)
        )
        persistence = _bounded(numeric_parameter(parameters, "persistence_count", 1) / 3)
        recurrence = _bounded(numeric_parameter(parameters, "recurrence_count", 1) / 3)
        trust_modifier = _bounded(numeric_parameter(parameters, "trust_modifier", 1.0))
        weights = {
            "deviation": 0.35,
            "confidence": 0.20,
            "materiality": 0.25,
            "persistence": 0.10,
            "recurrence": 0.05,
            "trust": 0.05,
        }
        raw = {
            "deviation": deviation_score,
            "confidence": confidence,
            "materiality": _bounded(materiality),
            "persistence": persistence,
            "recurrence": recurrence,
            "trust": trust_modifier,
        }
        components = tuple(
            ScoreComponent(
                code=code,
                raw_value=value,
                normalized_value=value,
                weight=weights[code],
                contribution=_bounded(value * weights[code]),
                explanation=f"Governed {code} contribution to bounded anomaly score",
            )
            for code, value in raw.items()
        )
        composite = _bounded(sum(item.raw_value * item.weight for item in components))
        business_score = _bounded(materiality)
        severity_value = composite * 0.55 + business_score * 0.45
        severity = (
            AnomalySeverity.CRITICAL
            if severity_value >= 0.85
            else AnomalySeverity.HIGH
            if severity_value >= 0.65
            else AnomalySeverity.MEDIUM
            if severity_value >= 0.4
            else AnomalySeverity.LOW
            if severity_value >= 0.2
            else AnomalySeverity.INFORMATIONAL
        )
        return AnomalyScore(composite, confidence, business_score, severity, components)


class FalsePositiveControlService:
    def should_suppress(
        self,
        db: Session,
        organization_id: UUID,
        definition_version_id: UUID,
        payload: StatisticalExecutionCreate,
        result: StatisticalMethodResult,
        score: AnomalyScore,
    ) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        parameters = payload.parameters
        last = payload.observations[-1]
        if last.known_event:
            reasons.append("known_event_exclusion")
        if last.planned_maintenance:
            reasons.append("planned_maintenance_exclusion")
        if last.approved_business_event:
            reasons.append("approved_business_event_exclusion")
        if integer_parameter(parameters, "persistence_count", 1) < integer_parameter(
            parameters, "minimum_persistence", 1
        ):
            reasons.append("minimum_persistence")
        if score.confidence_score < numeric_parameter(parameters, "minimum_confidence", 0.0):
            reasons.append("minimum_confidence")
        if score.materiality_score < numeric_parameter(parameters, "minimum_materiality", 0.0):
            reasons.append("minimum_materiality")
        if abs(result.normalized_deviation or 0.0) < numeric_parameter(
            parameters, "minimum_deviation", 0.0
        ):
            reasons.append("minimum_deviation")
        now = datetime.now(UTC)
        active = db.scalar(
            select(AnomalySuppressionRecord).where(
                AnomalySuppressionRecord.organization_id == organization_id,
                AnomalySuppressionRecord.definition_version_id == definition_version_id,
                or_(
                    AnomalySuppressionRecord.entity_reference.is_(None),
                    AnomalySuppressionRecord.entity_reference == last.entity_reference,
                ),
                AnomalySuppressionRecord.effective_from <= now,
                or_(
                    AnomalySuppressionRecord.effective_to.is_(None),
                    AnomalySuppressionRecord.effective_to > now,
                ),
            )
        )
        if active is not None:
            reasons.append("active_suppression")
        return bool(reasons), reasons


class StatisticalEvidenceBuilder:
    @staticmethod
    def build(
        execution: StatisticalExecution,
        baseline: StatisticalBaseline,
        result: StatisticalMethodResult,
        score: AnomalyScore,
    ) -> list[dict[str, object]]:
        return [
            {
                "evidence_type": "statistical_execution_trace",
                "execution_id": str(execution.id),
                "dataset_reference": execution.dataset_reference,
                "dataset_fingerprint": execution.dataset_fingerprint,
                "lineage_reference": execution.source_lineage_reference,
                "trust_assessment_id": str(execution.trust_assessment_id),
                "readiness_assessment_id": str(execution.readiness_assessment_id),
                "oikb_definition_version_id": str(execution.oikb_definition_version_id),
                "execution_package_fingerprint": execution.execution_package_fingerprint,
                "baseline_fingerprint": baseline.baseline_fingerprint,
                "method": f"{execution.method_code}:{execution.method_version}",
                "normalized_deviation": result.normalized_deviation,
                "statistical_score": score.statistical_score,
                "aggregate_only": True,
            }
        ]


class StatisticalExecutionService:
    def __init__(
        self,
        registry: StatisticalMethodRegistry | None = None,
        baseline_service: BaselineService | None = None,
        scoring_service: AnomalyScoringService | None = None,
        controls: FalsePositiveControlService | None = None,
        evidence_builder: StatisticalEvidenceBuilder | None = None,
    ) -> None:
        self.registry = registry or default_statistical_method_registry()
        self.baselines = baseline_service or BaselineService()
        self.scoring = scoring_service or AnomalyScoringService()
        self.controls = controls or FalsePositiveControlService()
        self.evidence = evidence_builder or StatisticalEvidenceBuilder()

    def evaluate(self, payload: StatisticalEvaluateRequest) -> StatisticalEvaluationRead:
        try:
            method = self.registry.get(payload.method_code, payload.method_version)
            values = finite_values(list(payload.values))
            result = method.execute(values, payload.parameters)
        except InsufficientStatisticalDataError as exc:
            return self._evaluation_error(
                payload, StatisticalExecutionStatus.INSUFFICIENT_DATA, "INSUFFICIENT_DATA", str(exc)
            )
        except UnsupportedStatisticalMethodError as exc:
            return self._evaluation_error(
                payload, StatisticalExecutionStatus.UNSUPPORTED, "UNSUPPORTED_METHOD", str(exc)
            )
        except StatisticalMethodError as exc:
            return self._evaluation_error(
                payload, StatisticalExecutionStatus.FAILED, "INVALID_STATISTICAL_INPUT", str(exc)
            )
        return StatisticalEvaluationRead(
            status=StatisticalExecutionStatus.SUCCEEDED,
            method=StatisticalMethodRead(**asdict(method.metadata)),
            observed_value=result.observed_value,
            expected_value=result.expected_value,
            normalized_deviation=result.normalized_deviation,
            is_anomaly=result.is_anomaly,
            threshold=result.threshold,
            summary=result.summary,
            explanation="Bounded registered statistical method executed deterministically.",
        )

    def execute(
        self,
        db: Session,
        organization_id: UUID,
        payload: StatisticalExecutionCreate,
        actor_user_id: UUID,
    ) -> StatisticalExecution:
        try:
            provenance = governed_dataset_provenance_service.resolve(
                db, organization_id, payload.dataset_id, payload.dataset_version_id
            )
        except GovernedProvenanceError as exc:
            raise StatisticalServiceError(exc.code, str(exc), http_status=exc.http_status) from exc
        existing = db.scalar(
            select(StatisticalExecution).where(
                StatisticalExecution.organization_id == organization_id,
                StatisticalExecution.idempotency_key == payload.idempotency_key,
            )
        )
        request_fingerprint = _hash(
            {
                "organization_id": organization_id,
                "payload": payload.model_dump(mode="json"),
                "provenance": provenance.identity(),
            }
        )
        if existing is not None:
            if existing.reproducibility_fingerprint != request_fingerprint:
                raise StatisticalServiceError(
                    "IDEMPOTENCY_CONFLICT",
                    "Idempotency key is already bound to different immutable inputs",
                    http_status=409,
                )
            return existing
        resolved = knowledge_resolution_service.resolve(
            db,
            ResolveRequest(
                organization_id=organization_id,
                stable_code=payload.definition_code,
                industry_pack_code=payload.industry_pack_code,
                region_code=payload.region_code,
            ),
        )
        if (
            resolved is None
            or resolved.version.semantic_version != payload.definition_version
            or resolved.definition.analytical_level != AnalyticalLevel.STATISTICAL.value
        ):
            raise StatisticalServiceError(
                "DEFINITION_NOT_ELIGIBLE",
                "Active statistical definition was not found",
                http_status=404,
            )
        package = execution_package_export_service.export(
            db, resolved.version, resolved.trace.model_dump(mode="json")
        )
        method_code = str(resolved.version.expression_schema.get("operation", "")).upper()
        method_version = str(resolved.version.expression_schema.get("method_version", "1.0"))
        execution = StatisticalExecution(
            organization_id=organization_id,
            orchestration_request_id=payload.orchestration_request_id,
            oikb_definition_id=resolved.definition.id,
            oikb_definition_version_id=resolved.version.id,
            execution_package_fingerprint=package.fingerprint,
            reproducibility_fingerprint=request_fingerprint,
            method_code=method_code,
            method_version=method_version,
            status=StatisticalExecutionStatus.PENDING.value,
            requested_by=actor_user_id,
            trust_assessment_id=payload.trust_assessment_id,
            readiness_assessment_id=payload.readiness_assessment_id,
            dataset_id=provenance.dataset_id,
            dataset_version_id=provenance.dataset_version_id,
            ingestion_batch_id=provenance.ingestion_batch_id,
            source_system_id=provenance.source_system_id,
            dataset_reference=provenance.dataset_reference,
            dataset_fingerprint=provenance.dataset_fingerprint,
            source_lineage_reference=provenance.source_lineage_reference,
            parameter_snapshot=dict(payload.parameters),
            engine_version=ENGINE_VERSION,
            correlation_id=payload.correlation_id,
            idempotency_key=payload.idempotency_key,
            warnings=[],
            limitations=[
                "Anomaly indicates governed deviation, not causation or misconduct",
                "Raw canonical observations are not persisted",
            ],
        )
        db.add(execution)
        db.flush()
        try:
            self._step(db, execution, 1, "governance", "completed", "Active OIKB package resolved")
            readiness_error = self._readiness(
                db,
                organization_id,
                payload.trust_assessment_id,
                payload.readiness_assessment_id,
                provenance,
            )
            if readiness_error is not None:
                execution.status = readiness_error[0].value
                execution.blocked_reason = readiness_error[1]
                self._step(db, execution, 2, "readiness", "blocked", readiness_error[1])
                execution.completed_at = datetime.now(UTC)
                db.commit()
                db.refresh(execution)
                return execution
            execution.status = StatisticalExecutionStatus.RUNNING.value
            execution.started_at = datetime.now(UTC)
            self._step(
                db, execution, 2, "readiness", "completed", "Statistical readiness confirmed"
            )
            method = self.registry.get(method_code, method_version)
            values, missing_percentage = self._validated_values(payload, method.metadata)
            maximum_missing = numeric_parameter(
                payload.parameters,
                "maximum_missing_percentage",
                float(
                    str(
                        resolved.version.readiness_requirement.get(
                            "maximum_missing_percentage",
                            MAX_MISSING_PERCENTAGE_DEFAULT,
                        )
                    )
                ),
            )
            if missing_percentage > maximum_missing:
                raise InsufficientStatisticalDataError(
                    "Missingness exceeds the governed statistical threshold"
                )
            baseline_type = str(
                payload.parameters.get(
                    "baseline_type",
                    resolved.version.expression_schema.get("baseline_type", "historical_self"),
                )
            ).lower()
            if method.metadata.supports_peer_group:
                minimum_peer_count = integer_parameter(payload.parameters, "minimum_peer_count", 5)
                if (
                    len({item.entity_reference for item in payload.observations})
                    < minimum_peer_count
                ):
                    raise InsufficientStatisticalDataError(
                        "Peer group is below the governed minimum count"
                    )
                baseline_type = "peer_group"
            baseline = self.baselines.build(execution, values, payload, baseline_type)
            db.add(baseline)
            db.flush()
            result = method.execute(values, payload.parameters)
            materiality = payload.observations[-1].materiality
            score = self.scoring.score(result, materiality, len(values), payload.parameters)
            suppressed, reasons = self.controls.should_suppress(
                db, organization_id, resolved.version.id, payload, result, score
            )
            observation = self._observation(
                execution,
                payload,
                method.metadata,
                result,
                score,
                baseline,
                suppressed,
                reasons,
            )
            db.add(observation)
            db.flush()
            for component in score.components:
                db.add(
                    StatisticalScoreComponent(
                        statistical_observation_id=observation.id,
                        component_code=component.code,
                        raw_value=component.raw_value,
                        normalized_value=component.normalized_value,
                        weight=component.weight,
                        contribution=component.contribution,
                        explanation=component.explanation,
                    )
                )
            self._step(
                db,
                execution,
                3,
                "statistical_method",
                "completed",
                "Registered bounded method executed",
                output={"is_anomaly": observation.is_anomaly, "suppressed": suppressed},
            )
            execution.status = StatisticalExecutionStatus.SUCCEEDED.value
        except InsufficientStatisticalDataError as exc:
            execution.status = StatisticalExecutionStatus.INSUFFICIENT_DATA.value
            execution.blocked_reason = str(exc)
            self._step(db, execution, 3, "statistical_method", "blocked", str(exc))
        except UnsupportedStatisticalMethodError as exc:
            execution.status = StatisticalExecutionStatus.UNSUPPORTED.value
            execution.failure_code = "UNSUPPORTED_METHOD"
            execution.failure_message = str(exc)
            self._step(db, execution, 3, "statistical_method", "unsupported", str(exc))
        except StatisticalMethodError as exc:
            execution.status = StatisticalExecutionStatus.FAILED.value
            execution.failure_code = "INVALID_STATISTICAL_INPUT"
            execution.failure_message = str(exc)
            self._step(db, execution, 3, "statistical_method", "failed", str(exc))
        execution.completed_at = datetime.now(UTC)
        db.commit()
        db.refresh(execution)
        return execution

    @staticmethod
    def _validated_values(
        payload: StatisticalExecutionCreate, metadata: StatisticalMethodMetadata
    ) -> tuple[list[float], float]:
        supplied = [item.value for item in payload.observations]
        values = finite_values(supplied)
        missing = (len(supplied) - len(values)) * 100 / len(supplied)
        if len(values) < metadata.minimum_sample_size:
            raise InsufficientStatisticalDataError(
                f"{metadata.method_code} requires at least "
                f"{metadata.minimum_sample_size} observations"
            )
        if metadata.supports_time_series:
            timestamps = [item.timestamp for item in payload.observations]
            if any(item is None for item in timestamps):
                raise StatisticalMethodError("Time-series methods require timestamps")
            concrete = [item for item in timestamps if item is not None]
            if concrete != sorted(concrete):
                raise StatisticalMethodError(
                    "Time-series observations must be chronologically ordered"
                )
            if len(concrete) != len(set(concrete)):
                raise StatisticalMethodError("Duplicate timestamps are not supported")
            invalid_periods = {
                item.period_status
                for item in payload.observations
                if item.period_status != PeriodStatus.COMPLETE
            }
            if invalid_periods:
                raise InsufficientStatisticalDataError(
                    "Time-series contains incomplete, late, missing, duplicate, "
                    "or irregular periods"
                )
        return values, missing

    @staticmethod
    def _readiness(
        db: Session,
        organization_id: UUID,
        trust_assessment_id: UUID,
        readiness_assessment_id: UUID,
        provenance: GovernedDatasetProvenance,
    ) -> tuple[StatisticalExecutionStatus, str] | None:
        trust = db.scalar(
            select(TrustAssessment).where(
                TrustAssessment.id == trust_assessment_id,
                TrustAssessment.organization_id == organization_id,
            )
        )
        if (
            trust is None
            or trust.dataset_id != provenance.dataset_id
            or trust.status
            not in {
                TrustAssessmentStatus.COMPLETED.value,
                TrustAssessmentStatus.COMPLETED_WITH_WARNINGS.value,
            }
        ):
            return StatisticalExecutionStatus.BLOCKED, "Trust assessment is not eligible"
        readiness = db.scalar(
            select(AnalyticalReadinessDecision).where(
                AnalyticalReadinessDecision.id == readiness_assessment_id,
                AnalyticalReadinessDecision.organization_id == organization_id,
                AnalyticalReadinessDecision.trust_assessment_id == trust_assessment_id,
                AnalyticalReadinessDecision.analytical_level == AnalyticalLevel.STATISTICAL.value,
            )
        )
        if readiness is None:
            return (
                StatisticalExecutionStatus.NOT_READY,
                "Explicit statistical readiness is required",
            )
        if readiness.readiness_status not in {
            ReadinessStatus.READY.value,
            ReadinessStatus.READY_WITH_WARNINGS.value,
        }:
            return StatisticalExecutionStatus.NOT_READY, readiness.explanation
        return None

    def _observation(
        self,
        execution: StatisticalExecution,
        payload: StatisticalExecutionCreate,
        metadata: StatisticalMethodMetadata,
        result: StatisticalMethodResult,
        score: AnomalyScore,
        baseline: StatisticalBaseline,
        suppressed: bool,
        suppression_reasons: list[str],
    ) -> StatisticalObservation:
        absolute = (
            None if result.expected_value is None else result.observed_value - result.expected_value
        )
        relative = None
        expected = result.expected_value
        if expected is not None and expected != 0 and absolute is not None:
            relative = absolute / abs(expected)
        last = payload.observations[-1]
        direction = (
            AnomalyDirection.TREND_INCREASE
            if metadata.method_code == "LINEAR_TREND" and (result.normalized_deviation or 0) >= 0
            else AnomalyDirection.TREND_DECREASE
            if metadata.method_code == "LINEAR_TREND"
            else AnomalyDirection.LEVEL_SHIFT
            if metadata.method_code in {"LEVEL_SHIFT", "CUSUM_CHANGE_DETECTION"}
            else AnomalyDirection.ABOVE_EXPECTED
            if (absolute or 0) >= 0
            else AnomalyDirection.BELOW_EXPECTED
        )
        explanation = {
            "method_name": metadata.method_name,
            "method_version": metadata.method_version,
            "why_this_method": "Selected by an active governed OIKB statistical definition",
            "comparison_basis": baseline.baseline_type,
            "baseline_summary": {
                "fingerprint": baseline.baseline_fingerprint,
                "record_count": baseline.record_count,
                "median": baseline.median_value,
            },
            "sample_size": baseline.record_count,
            "time_window": [baseline.time_window_start, baseline.time_window_end],
            "peer_group_summary": (
                {"aggregate_only": True, "entity_count": baseline.entity_count}
                if metadata.supports_peer_group
                else None
            ),
            "observed_value": result.observed_value,
            "expected_value": result.expected_value,
            "deviation": absolute,
            "normalized_deviation": result.normalized_deviation,
            "threshold": result.threshold,
            "statistical_score": score.statistical_score,
            "confidence_score": score.confidence_score,
            "materiality_score": score.materiality_score,
            "severity": score.severity.value,
            "persistence": integer_parameter(payload.parameters, "persistence_count", 1),
            "recurrence": integer_parameter(payload.parameters, "recurrence_count", 1),
            "alternative_explanations": [
                "operational mix or timing",
                "data capture or mapping issue",
                "approved business event",
                "maintenance or process change",
            ],
            "known_limitations": list(execution.limitations),
            "recommended_verification": (
                "Review source lineage, operating context, unit continuity, and supporting records."
            ),
            "suppression_reasons": suppression_reasons,
        }
        observation = StatisticalObservation(
            organization_id=execution.organization_id,
            statistical_execution_id=execution.id,
            entity_reference=last.entity_reference,
            period_reference=last.period_reference,
            observed_value=result.observed_value,
            expected_value=result.expected_value,
            absolute_deviation=absolute,
            relative_deviation=relative,
            normalized_deviation=result.normalized_deviation,
            statistical_score=score.statistical_score,
            confidence_score=score.confidence_score,
            materiality_score=score.materiality_score,
            anomaly_direction=direction.value,
            severity=score.severity.value,
            is_anomaly=result.is_anomaly and not suppressed,
            persistence_count=integer_parameter(payload.parameters, "persistence_count", 1),
            recurrence_count=integer_parameter(payload.parameters, "recurrence_count", 1),
            method_trace={"metadata": asdict(metadata), "result": result.summary},
            explanation=explanation,
            limitations=list(execution.limitations),
            evidence_references=[],
        )
        observation.evidence_references = self.evidence.build(execution, baseline, result, score)
        return observation

    @staticmethod
    def _step(
        db: Session,
        execution: StatisticalExecution,
        sequence: int,
        code: str,
        status: str,
        explanation: str,
        *,
        output: dict[str, object] | None = None,
    ) -> None:
        db.add(
            StatisticalExecutionStep(
                statistical_execution_id=execution.id,
                sequence_number=sequence,
                step_code=code,
                status=status,
                completed_at=datetime.now(UTC),
                input_summary={},
                output_summary=output or {},
                explanation=explanation,
            )
        )

    def _evaluation_error(
        self,
        payload: StatisticalEvaluateRequest,
        status: StatisticalExecutionStatus,
        code: str,
        message: str,
    ) -> StatisticalEvaluationRead:
        metadata = (
            self.registry.get(payload.method_code, payload.method_version).metadata
            if status != StatisticalExecutionStatus.UNSUPPORTED
            else StatisticalMethodMetadata(
                payload.method_code,
                payload.method_code.replace("_", " ").title(),
                payload.method_version,
                "UNSUPPORTED",
                0,
            )
        )
        return StatisticalEvaluationRead(
            status=status,
            method=StatisticalMethodRead(**asdict(metadata)),
            observed_value=None,
            expected_value=None,
            normalized_deviation=None,
            is_anomaly=None,
            threshold=None,
            summary={},
            error_code=code,
            explanation=message,
        )

    def get(self, db: Session, organization_id: UUID, execution_id: UUID) -> StatisticalExecution:
        execution = db.scalar(
            select(StatisticalExecution).where(
                StatisticalExecution.id == execution_id,
                StatisticalExecution.organization_id == organization_id,
            )
        )
        if execution is None:
            raise StatisticalServiceError(
                "STATISTICAL_EXECUTION_NOT_FOUND",
                "Statistical execution not found",
                http_status=404,
            )
        return execution

    def list_executions(
        self,
        db: Session,
        organization_id: UUID,
        *,
        page: int,
        page_size: int,
        status: str | None = None,
    ) -> tuple[list[StatisticalExecution], int]:
        filters = [StatisticalExecution.organization_id == organization_id]
        if status is not None:
            filters.append(StatisticalExecution.status == status)
        total = (
            db.scalar(select(func.count()).select_from(StatisticalExecution).where(*filters)) or 0
        )
        items = list(
            db.scalars(
                select(StatisticalExecution)
                .where(*filters)
                .order_by(StatisticalExecution.created_at.desc(), StatisticalExecution.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return items, total

    def baselines_for(
        self, db: Session, organization_id: UUID, execution_id: UUID
    ) -> list[StatisticalBaseline]:
        self.get(db, organization_id, execution_id)
        return list(
            db.scalars(
                select(StatisticalBaseline).where(
                    StatisticalBaseline.organization_id == organization_id,
                    StatisticalBaseline.statistical_execution_id == execution_id,
                )
            )
        )

    def observations_for(
        self, db: Session, organization_id: UUID, execution_id: UUID
    ) -> list[StatisticalObservation]:
        self.get(db, organization_id, execution_id)
        return list(
            db.scalars(
                select(StatisticalObservation).where(
                    StatisticalObservation.organization_id == organization_id,
                    StatisticalObservation.statistical_execution_id == execution_id,
                )
            )
        )

    def steps_for(
        self, db: Session, organization_id: UUID, execution_id: UUID
    ) -> list[StatisticalExecutionStep]:
        self.get(db, organization_id, execution_id)
        return list(
            db.scalars(
                select(StatisticalExecutionStep)
                .where(StatisticalExecutionStep.statistical_execution_id == execution_id)
                .order_by(StatisticalExecutionStep.sequence_number)
            )
        )

    def observation(
        self, db: Session, organization_id: UUID, observation_id: UUID
    ) -> StatisticalObservation:
        item = db.scalar(
            select(StatisticalObservation).where(
                StatisticalObservation.id == observation_id,
                StatisticalObservation.organization_id == organization_id,
            )
        )
        if item is None:
            raise StatisticalServiceError(
                "STATISTICAL_OBSERVATION_NOT_FOUND",
                "Statistical observation not found",
                http_status=404,
            )
        return item

    def review(
        self,
        db: Session,
        organization_id: UUID,
        observation_id: UUID,
        payload: ObservationReviewCreate,
        reviewer_id: UUID,
    ) -> AnomalyReviewFeedback:
        self.observation(db, organization_id, observation_id)
        review = AnomalyReviewFeedback(
            organization_id=organization_id,
            statistical_observation_id=observation_id,
            reviewer_id=reviewer_id,
            **payload.model_dump(),
        )
        db.add(review)
        db.commit()
        db.refresh(review)
        return review

    def suppress(
        self,
        db: Session,
        organization_id: UUID,
        observation_id: UUID,
        payload: ObservationSuppressionCreate,
        actor_id: UUID,
    ) -> AnomalySuppressionRecord:
        observation = self.observation(db, organization_id, observation_id)
        execution = self.get(db, organization_id, observation.statistical_execution_id)
        suppression = AnomalySuppressionRecord(
            organization_id=organization_id,
            definition_version_id=execution.oikb_definition_version_id,
            entity_reference=observation.entity_reference,
            created_by=actor_id,
            **payload.model_dump(),
        )
        db.add(suppression)
        db.commit()
        db.refresh(suppression)
        return suppression

    def sync_method_registry(self, db: Session) -> list[StatisticalMethodRegistration]:
        for method in self.registry.list():
            metadata = method.metadata
            existing = db.scalar(
                select(StatisticalMethodRegistration).where(
                    StatisticalMethodRegistration.method_code == metadata.method_code,
                    StatisticalMethodRegistration.method_version == metadata.method_version,
                )
            )
            values = {
                "method_name": metadata.method_name,
                "capability_class": metadata.capability_class,
                "supported": True,
                "minimum_sample_size": metadata.minimum_sample_size,
                "supports_time_series": metadata.supports_time_series,
                "supports_peer_group": metadata.supports_peer_group,
                "supports_grouping": metadata.supports_grouping,
                "supports_weights": metadata.supports_weights,
                "parameter_schema": {"bounded": True, "arbitrary_code": False},
                "output_schema": {"explainable": True, "finite_numeric": True},
                "implementation_reference": "app.engines.statistical_engine",
            }
            if existing is None:
                db.add(
                    StatisticalMethodRegistration(
                        method_code=metadata.method_code,
                        method_version=metadata.method_version,
                        **values,
                    )
                )
            else:
                for key, value in values.items():
                    setattr(existing, key, value)
        db.commit()
        return list(
            db.scalars(
                select(StatisticalMethodRegistration).order_by(
                    StatisticalMethodRegistration.method_code
                )
            )
        )


statistical_execution_service = StatisticalExecutionService()
