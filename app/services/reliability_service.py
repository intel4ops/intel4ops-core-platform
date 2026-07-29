from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.engines.reliability_engine import (
    ReliabilityMethodError,
    ReliabilityMethodRegistry,
    default_reliability_method_registry,
)
from app.models.oikb import OIKBDefinition, OIKBDefinitionVersion
from app.models.reliability import (
    ReliabilityExecution,
    ReliabilityExecutionStatus,
    ReliabilityExecutionStep,
    ReliabilityMetric,
    ReliabilityModelResult,
    ReliabilityReviewFeedback,
)
from app.models.trust import (
    AnalyticalReadinessDecision,
    ReadinessStatus,
    TrustAssessment,
    TrustAssessmentStatus,
)
from app.schemas.reliability import (
    ReliabilityEvaluateRequest,
    ReliabilityEvaluationRead,
    ReliabilityExecutionCreate,
    ReliabilityReviewCreate,
)


class ReliabilityServiceError(ValueError):
    def __init__(self, code: str, message: str, http_status: int = 422) -> None:
        self.code = code
        self.http_status = http_status
        super().__init__(message)


def _hash(value: object) -> str:
    """Return SHA-256 over canonical UTF-8 JSON with sorted keys and compact separators."""
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")
    ).hexdigest()


class AssetLifecycleService:
    def fingerprint(self, payload: ReliabilityExecutionCreate) -> str:
        lifecycle = [
            {
                "asset": item.asset_reference,
                "state": item.lifecycle_state,
                "censoring": item.censoring_status,
                "duration": item.duration,
            }
            for item in sorted(payload.observations, key=lambda item: item.asset_reference)
        ]
        if any(item.lifecycle_state == "UNKNOWN" for item in payload.observations):
            raise ReliabilityServiceError("INVALID_LIFECYCLE", "Unknown lifecycle blocks execution")
        return _hash(lifecycle)


class ReliabilityReadinessService:
    def validate(
        self,
        db: Session,
        organization_id: UUID,
        payload: ReliabilityExecutionCreate,
    ) -> tuple[TrustAssessment, AnalyticalReadinessDecision]:
        trust = db.scalar(
            select(TrustAssessment).where(
                TrustAssessment.id == payload.trust_assessment_id,
                TrustAssessment.organization_id == organization_id,
            )
        )
        if trust is None or trust.status != TrustAssessmentStatus.COMPLETED.value:
            raise ReliabilityServiceError(
                "TRUST_BLOCKED", "Completed tenant trust assessment required"
            )
        readiness = db.scalar(
            select(AnalyticalReadinessDecision).where(
                AnalyticalReadinessDecision.id == payload.readiness_assessment_id,
                AnalyticalReadinessDecision.organization_id == organization_id,
                AnalyticalReadinessDecision.trust_assessment_id == trust.id,
                AnalyticalReadinessDecision.analytical_level == "reliability",
            )
        )
        if readiness is None:
            raise ReliabilityServiceError(
                "READINESS_NOT_FOUND", "Reliability readiness not found", 404
            )
        if readiness.readiness_status not in {
            ReadinessStatus.READY.value,
            ReadinessStatus.READY_WITH_WARNINGS.value,
        }:
            raise ReliabilityServiceError("NOT_READY", readiness.explanation)
        return trust, readiness


class ReliabilityExecutionService:
    engine_version = "1.0.0"

    def __init__(self, registry: ReliabilityMethodRegistry | None = None) -> None:
        self.registry = registry or default_reliability_method_registry()
        self.readiness = ReliabilityReadinessService()
        self.lifecycle = AssetLifecycleService()

    def evaluate(self, payload: ReliabilityEvaluateRequest) -> ReliabilityEvaluationRead:
        try:
            method = self.registry.get(payload.method_code, payload.method_version)
            inputs = [
                item.model_dump(exclude_none=True, mode="json") for item in payload.observations
            ]
            result = method.execute(inputs)
        except ReliabilityMethodError as exc:
            raise ReliabilityServiceError("METHOD_REJECTED", str(exc)) from exc
        return ReliabilityEvaluationRead(
            status="succeeded",
            method_code=method.metadata.method_code,
            method_version=method.metadata.method_version,
            values=result.values,
            diagnostics=result.diagnostics,
            limitations=list(result.limitations),
        )

    def _execution_package_fingerprint(
        self,
        definition: OIKBDefinition,
        version: OIKBDefinitionVersion,
        payload: ReliabilityExecutionCreate,
    ) -> str:
        return _hash(
            {
                "governed_definition": {
                    "stable_code": definition.stable_code,
                    "definition_id": definition.id,
                    "semantic_version": version.semantic_version,
                    "version_id": version.id,
                    "version_fingerprint": version.fingerprint,
                },
                "method": [payload.method_code, payload.method_version],
                "failure_definition": [
                    payload.failure_definition_code,
                    payload.failure_definition_version,
                ],
                "exposure_basis": payload.exposure_basis,
                "censoring_policy": payload.censoring_policy,
            }
        )

    def _reproducibility_fingerprint(
        self,
        organization_id: UUID,
        payload: ReliabilityExecutionCreate,
        readiness: AnalyticalReadinessDecision,
        lifecycle_fingerprint: str,
        inputs: list[dict[str, object]],
        package: str,
    ) -> str:
        return _hash(
            {
                "organization": organization_id,
                "asset_scope": payload.asset_scope_reference,
                "asset_scope_type": payload.asset_scope_type,
                "trust_assessment": payload.trust_assessment_id,
                "orchestration_request": payload.orchestration_request_id,
                "dataset_reference": payload.dataset_reference,
                "dataset": payload.dataset_fingerprint,
                "source_lineage_reference": payload.source_lineage_reference,
                "lifecycle": lifecycle_fingerprint,
                "window": [payload.observation_window_start, payload.observation_window_end],
                "exposure_unit": payload.exposure_unit,
                "package": package,
                "readiness": readiness.id,
                "inputs": inputs,
                "engine": self.engine_version,
            }
        )

    @staticmethod
    def _verified_replay(
        existing: ReliabilityExecution,
        definition: OIKBDefinition,
        version: OIKBDefinitionVersion,
        package: str,
    ) -> ReliabilityExecution:
        if (
            existing.oikb_definition_id != definition.id
            or existing.oikb_definition_version_id != version.id
            or existing.execution_package_fingerprint != package
            or definition.stable_code == ""
            or version.semantic_version == ""
            or version.fingerprint == ""
        ):
            raise ReliabilityServiceError(
                "IDEMPOTENCY_CONFLICT",
                "Existing reliability execution does not match governed definition identity",
                409,
            )
        return existing

    def execute(
        self,
        db: Session,
        organization_id: UUID,
        payload: ReliabilityExecutionCreate,
        actor: UUID,
    ) -> ReliabilityExecution:
        _, readiness = self.readiness.validate(db, organization_id, payload)
        definition = db.scalar(
            select(OIKBDefinition).where(
                OIKBDefinition.stable_code == payload.definition_code,
                (
                    (OIKBDefinition.owner_organization_id.is_(None))
                    | (OIKBDefinition.owner_organization_id == organization_id)
                ),
            )
        )
        if definition is None or definition.analytical_level != "reliability":
            raise ReliabilityServiceError(
                "DEFINITION_NOT_FOUND", "Reliability definition not found", 404
            )
        version = db.scalar(
            select(OIKBDefinitionVersion).where(
                OIKBDefinitionVersion.definition_id == definition.id,
                OIKBDefinitionVersion.semantic_version == payload.definition_version,
                OIKBDefinitionVersion.lifecycle_status == "active",
            )
        )
        if version is None:
            raise ReliabilityServiceError(
                "INACTIVE_DEFINITION", "Active definition version required"
            )
        try:
            method = self.registry.get(payload.method_code, payload.method_version)
        except ReliabilityMethodError as exc:
            raise ReliabilityServiceError("UNSUPPORTED_METHOD", str(exc)) from exc
        lifecycle_fingerprint = self.lifecycle.fingerprint(payload)
        inputs = [item.model_dump(mode="json") for item in payload.observations]
        total_exposure = sum(item.exposure for item in payload.observations)
        failures = sum(item.failure_count for item in payload.observations)
        if len(payload.observations) < method.metadata.minimum_asset_count:
            raise ReliabilityServiceError("INSUFFICIENT_ASSETS", "Minimum asset count not met")
        if failures < method.metadata.minimum_failure_count:
            raise ReliabilityServiceError("INSUFFICIENT_FAILURES", "Minimum failure count not met")
        if total_exposure < method.metadata.minimum_exposure:
            raise ReliabilityServiceError("INSUFFICIENT_EXPOSURE", "Minimum exposure not met")
        if payload.exposure_basis not in method.metadata.supported_exposure_bases:
            raise ReliabilityServiceError("INVALID_EXPOSURE_BASIS", "Exposure basis is unsupported")
        package = self._execution_package_fingerprint(
            definition,
            version,
            payload,
        )
        reproducibility = self._reproducibility_fingerprint(
            organization_id,
            payload,
            readiness,
            lifecycle_fingerprint,
            inputs,
            package,
        )
        existing = db.scalar(
            select(ReliabilityExecution).where(
                ReliabilityExecution.organization_id == organization_id,
                ReliabilityExecution.reproducibility_fingerprint == reproducibility,
            )
        )
        if existing is not None:
            return self._verified_replay(existing, definition, version, package)
        now = datetime.now(UTC)
        execution = ReliabilityExecution(
            organization_id=organization_id,
            orchestration_request_id=payload.orchestration_request_id,
            oikb_definition_id=definition.id,
            oikb_definition_version_id=version.id,
            trust_assessment_id=payload.trust_assessment_id,
            readiness_assessment_id=payload.readiness_assessment_id,
            execution_package_fingerprint=package,
            reproducibility_fingerprint=reproducibility,
            asset_scope_reference=payload.asset_scope_reference,
            asset_scope_type=payload.asset_scope_type,
            reliability_method_code=payload.method_code,
            reliability_method_version=payload.method_version,
            status=ReliabilityExecutionStatus.RUNNING.value,
            requested_by=actor,
            started_at=now,
            dataset_reference=payload.dataset_reference,
            dataset_fingerprint=payload.dataset_fingerprint,
            lifecycle_fingerprint=lifecycle_fingerprint,
            source_lineage_reference=payload.source_lineage_reference,
            observation_window_start=payload.observation_window_start,
            observation_window_end=payload.observation_window_end,
            exposure_basis=payload.exposure_basis,
            exposure_unit=payload.exposure_unit,
            failure_definition_code=payload.failure_definition_code,
            failure_definition_version=payload.failure_definition_version,
            censoring_policy=payload.censoring_policy,
            engine_version=self.engine_version,
            correlation_id=payload.correlation_id,
            explanation={},
            warnings=list(readiness.warning_rule_codes),
            limitations=[],
        )
        db.add(execution)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            existing = db.scalar(
                select(ReliabilityExecution).where(
                    ReliabilityExecution.organization_id == organization_id,
                    ReliabilityExecution.reproducibility_fingerprint == reproducibility,
                )
            )
            if existing is None:
                raise
            return self._verified_replay(existing, definition, version, package)
        try:
            result = method.execute(inputs)
        except ReliabilityMethodError as exc:
            execution.status = ReliabilityExecutionStatus.FAILED.value
            execution.failure_code = "METHOD_REJECTED"
            execution.failure_message = str(exc)
            db.commit()
            raise ReliabilityServiceError("METHOD_REJECTED", str(exc)) from exc
        for code, value in result.values.items():
            db.add(
                ReliabilityMetric(
                    organization_id=organization_id,
                    reliability_execution_id=execution.id,
                    metric_code=code,
                    metric_value=value,
                    metric_unit=self._metric_unit(code, payload.exposure_unit),
                    numerator_value=float(failures) if code == "FAILURE_RATE" else None,
                    denominator_value=total_exposure if code == "FAILURE_RATE" else None,
                    exposure_basis=payload.exposure_basis,
                    confidence_score=min(1.0, len(inputs) / 10),
                    materiality_score=None,
                    valid=value is not None,
                    invalid_reason=None if value is not None else "NOT_ESTIMABLE",
                    method_trace={
                        "method_code": payload.method_code,
                        "version": payload.method_version,
                    },
                )
            )
        db.add(
            ReliabilityModelResult(
                organization_id=organization_id,
                reliability_execution_id=execution.id,
                method_code=payload.method_code,
                method_version=payload.method_version,
                parameter_values=result.values,
                fit_diagnostics=result.diagnostics,
                sample_size=len(inputs),
                failure_count=failures,
                censored_count=sum(not item.event_observed for item in payload.observations),
                validation_status="valid",
                limitations=list(result.limitations),
            )
        )
        db.add(
            ReliabilityExecutionStep(
                reliability_execution_id=execution.id,
                sequence_number=1,
                step_code="RELIABILITY_PIPELINE",
                status="succeeded",
                input_summary={"asset_count": len(inputs), "failure_count": failures},
                output_summary={"metric_count": len(result.values)},
                explanation=(
                    "Governed method executed after trust, readiness, lifecycle, "
                    "and exposure checks."
                ),
            )
        )
        execution.status = ReliabilityExecutionStatus.SUCCEEDED.value
        execution.completed_at = now
        execution.limitations = list(result.limitations)
        execution.explanation = {
            "asset_scope": payload.asset_scope_reference,
            "asset_class": payload.observations[0].asset_class,
            "failure_definition": payload.failure_definition_code,
            "exposure_basis": payload.exposure_basis,
            "observation_window": [
                payload.observation_window_start.isoformat(),
                payload.observation_window_end.isoformat(),
            ],
            "asset_count": len(inputs),
            "failure_count": failures,
            "maintenance_event_count": sum(item.repair_count for item in payload.observations),
            "censoring_summary": {
                status: sum(item.censoring_status == status for item in payload.observations)
                for status in sorted({item.censoring_status for item in payload.observations})
            },
            "selected_method": payload.method_code,
            "selected_method_version": payload.method_version,
            "why_this_method": "Selected by the active governed OIKB reliability definition.",
            "metric_summary": result.values,
            "model_parameters": result.values,
            "fit_diagnostics": result.diagnostics,
            "risk_score": result.values.get("RISK_SCORE"),
            "estimated_failure_probability": None,
            "confidence_score": min(1.0, len(inputs) / 10),
            "materiality_score": None,
            "severity": "INFORMATIONAL",
            "asset_health_score": result.values.get("ASSET_HEALTH_SCORE"),
            "alternative_explanations": [
                "Operating context or incomplete history may affect results."
            ],
            "known_limitations": list(result.limitations),
            "recommended_verification": (
                "Review lifecycle, work orders, exposure, and condition evidence."
            ),
            "recommended_action_category": "HUMAN_REVIEW",
            "human_review_required": True,
        }
        db.commit()
        db.refresh(execution)
        return execution

    @staticmethod
    def _metric_unit(code: str, exposure_unit: str) -> str:
        if code in {"FAILURE_RATE", "REPAIR_RATE"}:
            return f"1/{exposure_unit}"
        if code in {
            "MTBF",
            "MTTF",
            "MTTR",
            "EXPOSURE",
            "DOWNTIME",
            "MEDIAN_SURVIVAL",
            "B10",
            "B50",
        }:
            return exposure_unit
        if code.endswith("AVAILABILITY") or code.endswith("RATIO") or code == "FINAL_SURVIVAL":
            return "ratio"
        if code.endswith("SCORE"):
            return "score_0_100"
        return "count"

    def get(self, db: Session, organization_id: UUID, execution_id: UUID) -> ReliabilityExecution:
        row = db.scalar(
            select(ReliabilityExecution).where(
                ReliabilityExecution.id == execution_id,
                ReliabilityExecution.organization_id == organization_id,
            )
        )
        if row is None:
            raise ReliabilityServiceError("NOT_FOUND", "Reliability execution not found", 404)
        return row

    def list_executions(
        self, db: Session, organization_id: UUID, page: int, page_size: int
    ) -> tuple[list[ReliabilityExecution], int]:
        where = ReliabilityExecution.organization_id == organization_id
        total = db.scalar(select(func.count()).select_from(ReliabilityExecution).where(where)) or 0
        rows = list(
            db.scalars(
                select(ReliabilityExecution)
                .where(where)
                .order_by(ReliabilityExecution.created_at.desc(), ReliabilityExecution.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return rows, total

    def children(
        self, db: Session, organization_id: UUID, execution_id: UUID, model: Any
    ) -> list[object]:
        self.get(db, organization_id, execution_id)
        return list(
            db.scalars(
                select(model)
                .where(model.reliability_execution_id == execution_id)
                .order_by(getattr(model, "created_at", model.id), model.id)
            )
        )

    def review(
        self,
        db: Session,
        organization_id: UUID,
        execution_id: UUID,
        payload: ReliabilityReviewCreate,
        reviewer: UUID,
    ) -> ReliabilityReviewFeedback:
        self.get(db, organization_id, execution_id)
        row = ReliabilityReviewFeedback(
            organization_id=organization_id,
            reliability_execution_id=execution_id,
            reviewer_id=reviewer,
            **payload.model_dump(),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row


reliability_execution_service = ReliabilityExecutionService()
