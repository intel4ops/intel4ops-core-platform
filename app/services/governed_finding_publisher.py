from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analysis_case import FindingSourceDataset
from app.models.entities import Finding
from app.models.intelligence import (
    IntelligenceExecution,
    IntelligenceExecutionStatus,
    IntelligenceExecutionType,
)
from app.models.trust import AnalyticalLevel, AnalyticalReadinessDecision, ReadinessStatus
from app.schemas.findings import (
    CandidateFindingCreate,
    ConfidenceLevel,
    EvidenceItemCreate,
    EvidenceType,
    FindingSeverity,
    FindingType,
    FindingValueType,
    RuleTraceCreate,
)
from app.services.finding_platform_service import FindingPlatformError, finding_publication_service


def _hash(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


@dataclass(frozen=True)
class ContributingDataset:
    dataset_id: UUID
    dataset_version_id: UUID | None = None


@dataclass(frozen=True)
class GovernedFindingRequest:
    organization_id: UUID
    primary_dataset_id: UUID
    trust_assessment_id: UUID
    definition_code: str
    definition_version: str
    rule_condition_code: str
    affected_record_count: int
    title: str
    summary: str
    domain_code: str
    severity: FindingSeverity
    finding_type: FindingType
    actor_user_id: UUID
    contributing_datasets: list[ContributingDataset] = field(default_factory=list)
    entities: list[dict[str, object]] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    economic_status: str = "governed_pending"
    limitations: list[str] = field(default_factory=list)


class IntelligenceReadinessUnavailable(RuntimeError):
    """Raised when no READY/READY_WITH_WARNINGS arithmetic readiness
    decision exists for the backing trust assessment -- a rule must not
    fabricate a finding without a governed readiness gate to point at."""


class GovernedFindingPublisher:
    """Shared publication path for every P3.xxC.1 domain and cross-domain
    rule. Never publishes a fabricated economic value: measured_value is
    always a real observed count, exposure_value is always None unless a
    directly observed, currency-resolved figure is supplied by the caller
    (none of the P3.xxC.1 rules do this). Reuses the existing governed
    IntelligenceExecution/CandidateFindingCreate/FindingPublicationService
    pipeline unchanged -- no schema relaxation was needed (confirmed by
    investigation before implementation)."""

    def publish(self, db: Session, request: GovernedFindingRequest) -> Finding | None:
        readiness = db.scalar(
            select(AnalyticalReadinessDecision).where(
                AnalyticalReadinessDecision.organization_id == request.organization_id,
                AnalyticalReadinessDecision.trust_assessment_id == request.trust_assessment_id,
                AnalyticalReadinessDecision.analytical_level == AnalyticalLevel.ARITHMETIC.value,
                AnalyticalReadinessDecision.readiness_status.in_(
                    (ReadinessStatus.READY.value, ReadinessStatus.READY_WITH_WARNINGS.value)
                ),
            )
        )
        if readiness is None:
            return None

        now = datetime.now(UTC)
        definition_fingerprint = _hash(request.definition_code, request.definition_version)
        input_fingerprint = _hash(
            str(request.primary_dataset_id), str(request.affected_record_count), now.isoformat()
        )
        execution = IntelligenceExecution(
            organization_id=request.organization_id,
            dataset_id=request.primary_dataset_id,
            trust_assessment_id=request.trust_assessment_id,
            readiness_decision_id=readiness.id,
            execution_type=IntelligenceExecutionType.RULE.value,
            definition_code=request.definition_code,
            definition_version=request.definition_version,
            definition_fingerprint=definition_fingerprint,
            input_fingerprint=input_fingerprint,
            status=IntelligenceExecutionStatus.COMPLETED.value,
            result_value=Decimal(request.affected_record_count),
            unit=None,
            currency=None,
            breached=request.affected_record_count > 0,
            checked_record_count=max(request.affected_record_count, 1),
            affected_record_count=request.affected_record_count,
            exposure_value=None,
            exposure_currency=None,
            evaluation_time=now,
            created_by_user_id=request.actor_user_id,
            completed_at=now,
        )
        db.add(execution)
        db.flush()

        evidence = [
            EvidenceItemCreate(
                evidence_type=EvidenceType.DATASET,
                reference_type="dataset",
                reference_id=str(request.primary_dataset_id),
                label="Primary contributing dataset",
                dataset_id=request.primary_dataset_id,
            )
        ]
        for contributing in request.contributing_datasets:
            if contributing.dataset_id == request.primary_dataset_id:
                continue
            evidence.append(
                EvidenceItemCreate(
                    evidence_type=EvidenceType.DATASET,
                    reference_type="dataset",
                    reference_id=str(contributing.dataset_id),
                    label="Contributing dataset",
                    dataset_id=contributing.dataset_id,
                )
            )

        payload = CandidateFindingCreate(
            execution_id=execution.id,
            result_id=execution.id,
            finding_type=request.finding_type,
            title=request.title,
            summary=request.summary,
            domain_code=request.domain_code,
            measured_value=Decimal(request.affected_record_count),
            measured_value_type=FindingValueType.COUNT,
            severity=request.severity,
            severity_reason={"basis": request.rule_condition_code},
            confidence_level=ConfidenceLevel.HIGH,
            affected_record_count=request.affected_record_count,
            dataset_reference=str(request.primary_dataset_id),
            evidence_policy_code="p3xxc1_analysis_case_default",
            evidence_policy_version="1.0",
            evidence=evidence,
            rule_traces=[
                RuleTraceCreate(
                    condition_code=request.rule_condition_code,
                    evaluation_result=request.affected_record_count > 0,
                    comparison_operator="greater_than",
                    threshold_summary={"threshold": 0},
                )
            ],
            limitations=request.limitations,
        )
        try:
            finding = finding_publication_service.publish_candidate_finding(
                db, request.organization_id, payload, request.actor_user_id
            )
        except FindingPlatformError:
            db.rollback()
            raise

        finding.economic_status = request.economic_status
        finding.entities_json = request.entities or None
        finding.domains_json = request.domains or None
        db.add(finding)

        for dataset_id in {
            request.primary_dataset_id,
            *[c.dataset_id for c in request.contributing_datasets],
        }:
            existing = db.scalar(
                select(FindingSourceDataset).where(
                    FindingSourceDataset.finding_id == finding.id,
                    FindingSourceDataset.dataset_id == dataset_id,
                )
            )
            if existing is None:
                db.add(
                    FindingSourceDataset(
                        organization_id=request.organization_id,
                        finding_id=finding.id,
                        dataset_id=dataset_id,
                    )
                )
        db.commit()
        db.refresh(finding)
        return finding


governed_finding_publisher = GovernedFindingPublisher()
