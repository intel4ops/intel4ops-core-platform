from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
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
from app.services.canonical_evidence_completeness import CanonicalEvidenceCompletenessResult
from app.services.finding_platform_service import FindingPlatformError, finding_publication_service


def _hash(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


@dataclass(frozen=True)
class StableFindingIdentityReference:
    """Stable business identity explicitly supplied by a capability.

    ``entities`` remains presentation and validation lineage and may contain
    contextual entries. Only references declared here participate in logical
    finding identity.
    """

    identity_role: Literal["subject", "material_condition"]
    reference_type: str
    canonical_reference: str
    canonical_entity: str | None = None


def _identity_evidence_items(
    references: list[StableFindingIdentityReference],
) -> list[EvidenceItemCreate]:
    """Normalize stable identity references into deterministic evidence."""
    normalized: dict[tuple[str, str], StableFindingIdentityReference] = {}
    for reference in references:
        reference_type = reference.reference_type.strip()
        canonical_reference = reference.canonical_reference.strip()
        if not reference_type or not canonical_reference:
            raise ValueError("Finding identity references require a type and canonical reference")
        key = (reference_type, canonical_reference)
        existing = normalized.get(key)
        if existing is not None and existing.identity_role != reference.identity_role:
            raise ValueError("A finding identity reference cannot have conflicting roles")
        normalized[key] = reference

    items: list[EvidenceItemCreate] = []
    for (reference_type, canonical_reference), reference in sorted(normalized.items()):
        canonical_entity = (reference.canonical_entity or "").strip() or None
        items.append(
            EvidenceItemCreate(
                evidence_type=EvidenceType.AFFECTED_RECORD,
                reference_type=reference_type,
                reference_id=canonical_reference,
                canonical_entity=canonical_entity,
                canonical_record_reference=canonical_reference,
                label=f"{reference.identity_role.replace('_', ' ').title()}: "
                f"{reference_type} {canonical_reference}",
                metadata={"identity_role": reference.identity_role},
            )
        )
    return items


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
    identity_references: list[StableFindingIdentityReference] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    economic_status: str = "governed_pending"
    limitations: list[str] = field(default_factory=list)
    # P3.xxI.2: optional, currency-scoped observed/estimated economic
    # exposure. CandidateFindingCreate already validates this triad
    # (exposure_value_type == CURRENCY requires exposure_currency;
    # exposure_currency is invalid without a value) -- this publisher
    # previously always passed exposure_value=None unconditionally,
    # matching every existing rule's own choice never to estimate a
    # dollar figure. Purely additive: omitted (None), every existing
    # caller's behavior is unchanged.
    exposure_value: Decimal | None = None
    exposure_value_type: FindingValueType | None = None
    exposure_currency: str | None = None
    # P3.xxI.2: additional evidence items a capability wants to attach
    # beyond the identity/dataset evidence this publisher already builds
    # -- e.g. the specific quantity/rate/invoice rows a calculated
    # exposure value was derived from. Appended as-is; never replaces or
    # reorders the existing evidence this publisher constructs.
    supporting_evidence: list[EvidenceItemCreate] = field(default_factory=list)
    # P3.xxV.2D: optional POST-SEMANTIC canonical evidence completeness
    # result (see app/services/canonical_evidence_completeness.py). When the
    # backing arithmetic readiness decision is BLOCKED for the single reason
    # "required_field_completeness" -- Trust's own RAW-field check, run
    # before mapping/semantic interpretation -- and this result independently
    # confirms every required canonical concept has governed evidence, that
    # specific blocking reason is treated as satisfied for publication
    # purposes. Every OTHER blocking reason (or a missing/incomplete
    # canonical_evidence_completeness) still blocks publication -- this is
    # additive, never a bypass of Trust as a whole.
    canonical_evidence_completeness: CanonicalEvidenceCompletenessResult | None = None


class IntelligenceReadinessUnavailable(RuntimeError):
    """Raised when no READY/READY_WITH_WARNINGS arithmetic readiness
    decision exists for the backing trust assessment -- a rule must not
    fabricate a finding without a governed readiness gate to point at."""


class GovernedFindingPublisher:
    """Shared publication path for every P3.xxC.1 domain and cross-domain
    rule. Never publishes a fabricated economic value: measured_value is
    always a real observed count; exposure_value is None unless the caller
    directly computed a currency-resolved figure from governed evidence
    (P3.xxI.2's revenue-variance capability is the first to do so -- every
    other rule still omits it). Reuses the existing governed
    IntelligenceExecution/CandidateFindingCreate/FindingPublicationService
    pipeline unchanged -- no schema relaxation was needed (confirmed by
    investigation before implementation)."""

    def publish(self, db: Session, request: GovernedFindingRequest) -> Finding | None:
        readiness = db.scalar(
            select(AnalyticalReadinessDecision).where(
                AnalyticalReadinessDecision.organization_id == request.organization_id,
                AnalyticalReadinessDecision.trust_assessment_id == request.trust_assessment_id,
                AnalyticalReadinessDecision.analytical_level == AnalyticalLevel.ARITHMETIC.value,
            )
        )
        if readiness is None:
            return None
        if readiness.readiness_status not in (
            ReadinessStatus.READY.value,
            ReadinessStatus.READY_WITH_WARNINGS.value,
        ):
            # P3.xxV.2D: the ONLY corrected path -- an ARITHMETIC decision
            # blocked for exactly one reason, Trust's early RAW-field
            # required_field_completeness rule, is not itself wrong (it
            # correctly reports the literal raw column is absent); it is
            # simply the wrong check for GOVERNED FINDING PUBLICATION, which
            # must judge canonical evidence, not raw column names. Any other
            # blocking reason (or no canonical_evidence_completeness result
            # at all, or that result itself reporting missing evidence)
            # still blocks publication -- Trust as a whole is never bypassed.
            corrected = (
                request.canonical_evidence_completeness is not None
                and request.canonical_evidence_completeness.satisfied
                and set(readiness.blocking_rule_codes or []) == {"required_field_completeness"}
            )
            if not corrected:
                return None
            # The ORIGINAL early-Trust decision (raw dataset quality) is
            # never mutated -- it still, correctly, reports blocked. A
            # SEPARATE, new AnalyticalReadinessDecision row is persisted
            # instead, reusing the exact same existing representation
            # (never a new evidence object) to record that, for GOVERNED
            # FINDING PUBLICATION specifically, canonical evidence was
            # independently confirmed complete. finding_platform_service's
            # own downstream re-validation re-reads readiness by id, so the
            # execution must reference THIS row, not the original blocked
            # one, for that re-validation to correctly succeed.
            assert request.canonical_evidence_completeness is not None
            readiness = AnalyticalReadinessDecision(
                organization_id=request.organization_id,
                trust_assessment_id=request.trust_assessment_id,
                analytical_level=AnalyticalLevel.ARITHMETIC.value,
                readiness_status=ReadinessStatus.READY_WITH_WARNINGS.value,
                blocking_rule_codes=[],
                warning_rule_codes=["canonical_evidence_completeness_corrected"],
                explanation=(
                    "Raw-field required_field_completeness blocked this trust assessment "
                    "(source columns use aliases of the required canonical concepts, e.g. "
                    "a work-order identifier column rather than the canonical concept name "
                    "itself). Canonical evidence completeness was independently confirmed: "
                    + ", ".join(
                        f"{field.canonical_field} <- {field.source_field} "
                        f"({field.semantic_status}, {field.semantic_confidence})"
                        for field in request.canonical_evidence_completeness.fields
                        if field.satisfied
                    )
                    + "."
                ),
            )
            db.add(readiness)
            db.flush()

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
            exposure_value=request.exposure_value,
            exposure_currency=request.exposure_currency,
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
        # P3.xxV.2J (Fix #7): explicitly declared subject/material-condition
        # identity participates through the platform's existing
        # affected-record evidence contract.
        evidence.extend(_identity_evidence_items(request.identity_references))
        # P3.xxI.2: capability-supplied calculation evidence (e.g. the
        # quantity/rate/invoice rows an exposure_value was derived from),
        # appended after the identity evidence this publisher already
        # builds.
        evidence.extend(request.supporting_evidence)

        payload = CandidateFindingCreate(
            execution_id=execution.id,
            result_id=execution.id,
            finding_type=request.finding_type,
            title=request.title,
            summary=request.summary,
            domain_code=request.domain_code,
            measured_value=Decimal(request.affected_record_count),
            measured_value_type=FindingValueType.COUNT,
            exposure_value=request.exposure_value,
            exposure_value_type=request.exposure_value_type,
            exposure_currency=request.exposure_currency,
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
