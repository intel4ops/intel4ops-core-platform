from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.engines.economics_engine import OpportunityStatus
from app.models.economics import (
    EconomicCalculation,
    OpportunityFinding,
    OpportunityOverlapMember,
    PrioritizationAssessment,
    RecoveryOpportunity,
)
from app.models.entities import Finding, FindingStatus, Organization, OrganizationStatus
from app.models.findings import FindingEvidenceBundle, FindingEvidenceItem
from app.models.ingestion import Dataset, IngestionBatch
from app.models.intelligence import IntelligenceExecution, IntelligenceExecutionStatus
from app.models.raw_lineage import LineageNode, RawRecordReference
from app.models.source_system import SourceSystem
from app.models.trust import (
    AnalyticalReadinessDecision,
    ReadinessStatus,
    TrustAssessment,
    TrustAssessmentStatus,
    TrustRuleResult,
)
from app.models.value_scan import DirectionalValueScan
from app.models.workspace import OrganizationChallenge, OrganizationObjective, OrganizationSystem
from app.services.governed_provenance_service import (
    GovernedProvenanceError,
    governed_dataset_provenance_service,
)

SCAN_POLICY_CODE = "DIRECTIONAL_VALUE_SCAN"
SCAN_POLICY_VERSION = "1.0"
RANKING_POLICY_CODE = "DIRECTIONAL_VALUE_SCAN_V1"
RANKING_POLICY_VERSION = "1.0"
MAX_CANDIDATE_FINDINGS = 1000
MAX_OPPORTUNITIES = 10
MAX_EVIDENCE_REFERENCES = 25
ELIGIBLE_FINDING_STATUSES = {
    FindingStatus.PUBLISHED.value,
    FindingStatus.CONFIRMED.value,
}
ACTIVE_OPPORTUNITY_STATUSES = {
    status.value
    for status in OpportunityStatus
    if status
    not in {
        OpportunityStatus.REJECTED,
        OpportunityStatus.SUPERSEDED,
        OpportunityStatus.CANCELLED,
    }
}
SEVERITY_RANK = {"critical": 5, "high": 4, "medium": 3, "low": 2, "info": 1}


class ValueScanServiceError(ValueError):
    def __init__(self, code: str, message: str, status: int = 422) -> None:
        self.code = code
        self.status = status
        super().__init__(message)


@dataclass(frozen=True)
class ScanAssembly:
    input_fingerprint: str
    request_fingerprint: str
    status: str
    candidate_finding_count: int
    opportunities: list[dict[str, object]]
    data_gaps: list[dict[str, object]]
    data_coverage: dict[str, object]
    trust_readiness: dict[str, object]
    customer_context: dict[str, object]
    next_investigation: dict[str, object] | None
    provenance: dict[str, object]
    limitations: list[str]
    result_content_hash: str


def _json_default(value: object) -> str:
    if isinstance(value, (datetime, UUID, Decimal)):
        return str(value)
    raise TypeError(f"Unsupported fingerprint value: {type(value).__name__}")


def _hash(value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=_json_default,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _timestamp(value: datetime | None) -> float:
    if value is None:
        return 0.0
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.timestamp()


def _value(value: Decimal | float | int | None) -> str | None:
    return None if value is None else str(value)


def _reference_key(model: type[Any], identifier: UUID) -> tuple[type[Any], UUID]:
    return model, identifier


class DirectionalValueScanService:
    def create(
        self,
        db: Session,
        organization_id: UUID,
        requested_by_user_id: UUID,
        idempotency_key: str,
    ) -> tuple[DirectionalValueScan, bool]:
        organization = db.scalar(
            select(Organization).where(
                Organization.id == organization_id,
                Organization.status == OrganizationStatus.ACTIVE.value,
            )
        )
        if organization is None:
            raise ValueScanServiceError(
                "ORGANIZATION_NOT_FOUND",
                "Organization is not eligible for a Directional Value Scan",
                404,
            )

        assembly = self._assemble(db, organization)
        existing_key = db.scalar(
            select(DirectionalValueScan).where(
                DirectionalValueScan.organization_id == organization_id,
                DirectionalValueScan.idempotency_key == idempotency_key,
            )
        )
        if existing_key is not None:
            if existing_key.request_fingerprint != assembly.request_fingerprint:
                raise ValueScanServiceError(
                    "IDEMPOTENCY_CONFLICT",
                    "Idempotency key is already bound to different governed inputs",
                    409,
                )
            return existing_key, self._is_current(existing_key, assembly)

        existing_input = db.scalar(
            select(DirectionalValueScan).where(
                DirectionalValueScan.organization_id == organization_id,
                DirectionalValueScan.input_fingerprint == assembly.input_fingerprint,
            )
        )
        if existing_input is not None:
            return existing_input, True

        row = DirectionalValueScan(
            organization_id=organization_id,
            requested_by_user_id=requested_by_user_id,
            idempotency_key=idempotency_key,
            request_fingerprint=assembly.request_fingerprint,
            input_fingerprint=assembly.input_fingerprint,
            ranking_policy_code=RANKING_POLICY_CODE,
            ranking_policy_version=RANKING_POLICY_VERSION,
            status=assembly.status,
            generated_at=datetime.now(UTC),
            candidate_finding_count=assembly.candidate_finding_count,
            opportunity_count=len(assembly.opportunities),
            data_gap_count=len(assembly.data_gaps),
            data_coverage_snapshot=assembly.data_coverage,
            trust_readiness_snapshot=assembly.trust_readiness,
            customer_context_snapshot=assembly.customer_context,
            opportunity_snapshot=assembly.opportunities,
            data_gap_snapshot=assembly.data_gaps,
            next_investigation_snapshot=assembly.next_investigation,
            provenance_snapshot=assembly.provenance,
            limitations=assembly.limitations,
            result_content_hash=assembly.result_content_hash,
        )
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            concurrent = db.scalar(
                select(DirectionalValueScan).where(
                    DirectionalValueScan.organization_id == organization_id,
                    (
                        (DirectionalValueScan.idempotency_key == idempotency_key)
                        | (DirectionalValueScan.input_fingerprint == assembly.input_fingerprint)
                    ),
                )
            )
            if concurrent is None:
                raise
            if (
                concurrent.idempotency_key == idempotency_key
                and concurrent.request_fingerprint != assembly.request_fingerprint
            ):
                raise ValueScanServiceError(
                    "IDEMPOTENCY_CONFLICT",
                    "Idempotency key is already bound to different governed inputs",
                    409,
                ) from None
            return concurrent, self._is_current(concurrent, assembly)
        db.refresh(row)
        return row, True

    def get(
        self,
        db: Session,
        organization_id: UUID,
        scan_id: UUID,
    ) -> tuple[DirectionalValueScan, bool]:
        row = db.scalar(
            select(DirectionalValueScan).where(
                DirectionalValueScan.id == scan_id,
                DirectionalValueScan.organization_id == organization_id,
            )
        )
        if row is None:
            raise ValueScanServiceError("SCAN_NOT_FOUND", "Directional Value Scan not found", 404)
        organization = db.scalar(
            select(Organization).where(
                Organization.id == organization_id,
                Organization.status == OrganizationStatus.ACTIVE.value,
            )
        )
        if organization is None:
            raise ValueScanServiceError("SCAN_NOT_FOUND", "Directional Value Scan not found", 404)
        current = self._assemble(db, organization)
        return row, self._is_current(row, current)

    @staticmethod
    def _is_current(row: DirectionalValueScan, assembly: ScanAssembly) -> bool:
        return row.input_fingerprint == assembly.input_fingerprint

    def _assemble(self, db: Session, organization: Organization) -> ScanAssembly:
        organization_id = organization.id
        context = self._context(db, organization)
        finding_total = int(
            db.scalar(
                select(func.count(Finding.id)).where(
                    Finding.organization_id == organization_id,
                    Finding.status.in_(ELIGIBLE_FINDING_STATUSES),
                    Finding.finding_code.is_not(None),
                )
            )
            or 0
        )
        findings = list(
            db.scalars(
                select(Finding)
                .where(
                    Finding.organization_id == organization_id,
                    Finding.status.in_(ELIGIBLE_FINDING_STATUSES),
                    Finding.finding_code.is_not(None),
                )
                .order_by(Finding.created_at.desc(), Finding.id)
                .limit(MAX_CANDIDATE_FINDINGS)
            )
        )
        truncated = finding_total > MAX_CANDIDATE_FINDINGS
        related = self._load_related(db, organization_id, findings)
        opportunities: list[dict[str, object]] = []
        gaps: list[dict[str, object]] = []
        provenance_findings: list[dict[str, object]] = []
        support_counts: Counter[str] = Counter()

        for finding in findings:
            opportunity, finding_gaps, finding_provenance = self._project_finding(
                db,
                organization_id,
                finding,
                related,
            )
            gaps.extend(finding_gaps)
            provenance_findings.append(finding_provenance)
            support_state = str(finding_provenance["support_state"])
            support_counts[support_state] += 1
            if opportunity is not None:
                opportunities.append(opportunity)

        opportunities.sort(key=self._ranking_key)
        for rank, opportunity in enumerate(opportunities[:MAX_OPPORTUNITIES], start=1):
            opportunity["rank"] = rank
        opportunities = opportunities[:MAX_OPPORTUNITIES]

        limitations: list[str] = []
        if truncated:
            limitation = (
                "Candidate universe was truncated at 1000 governed Findings; "
                "this scan does not claim complete enterprise coverage."
            )
            limitations.append(limitation)
            gaps.append(
                {
                    "gap_code": "CANDIDATE_LIMIT_REACHED",
                    "affected_analysis": SCAN_POLICY_CODE,
                    "support_state": "PARTIAL",
                    "missing_input": "candidate_capacity",
                    "why_it_matters": limitation,
                    "unlocks": "complete directional ranking coverage",
                    "remediation_guidance": (
                        "Narrow the governed scope or use a later scheduled scan profile."
                    ),
                    "priority": 1,
                    "references": [],
                    "limitations": [limitation],
                }
            )

        data_exists = bool(
            db.scalar(select(Dataset.id).where(Dataset.organization_id == organization_id).limit(1))
            or db.scalar(
                select(IngestionBatch.id)
                .where(IngestionBatch.organization_id == organization_id)
                .limit(1)
            )
        )
        completed_trust_exists = bool(
            db.scalar(
                select(TrustAssessment.id)
                .where(
                    TrustAssessment.organization_id == organization_id,
                    TrustAssessment.status.in_(
                        {
                            TrustAssessmentStatus.COMPLETED.value,
                            TrustAssessmentStatus.COMPLETED_WITH_WARNINGS.value,
                        }
                    ),
                )
                .limit(1)
            )
        )
        if not data_exists:
            gaps.append(
                self._organization_gap(
                    "NO_GOVERNED_DATA",
                    "No governed dataset or ingestion batch is available.",
                    "Connect and govern an operational dataset before running value analysis.",
                )
            )
        elif not completed_trust_exists and not findings:
            gaps.append(
                self._organization_gap(
                    "TRUST_NOT_ESTABLISHED",
                    "No completed Trust assessment supports value analysis.",
                    "Complete Trust assessment and analytical readiness evaluation.",
                )
            )

        if opportunities:
            partial = truncated or bool(gaps) or support_counts["PARTIAL"] > 0
            status = "partial" if partial else "completed"
        elif data_exists and completed_trust_exists and not findings and not gaps:
            status = "completed"
            limitations.append(
                "No eligible published or confirmed Findings exist; this is not a declaration "
                "that no operational problems exist."
            )
        else:
            status = "refused"
            if not gaps:
                gaps.append(
                    self._organization_gap(
                        "NO_SUPPORTED_ANALYSIS",
                        "No governed analysis is currently supportable.",
                        "Resolve the highest-priority Trust or provenance limitation.",
                    )
                )

        next_investigation = self._next_investigation(opportunities, gaps, status)
        currencies = sorted(
            {
                currency
                for opportunity in opportunities
                for currency in self._opportunity_currencies(opportunity)
                if currency
            }
        )
        data_coverage: dict[str, object] = {
            "data_available": data_exists,
            "eligible_finding_count": finding_total,
            "evaluated_finding_count": len(findings),
            "supported_opportunity_count": len(opportunities),
            "candidate_limit": MAX_CANDIDATE_FINDINGS,
            "candidate_universe_truncated": truncated,
            "currencies_present": currencies,
            "zero_opportunity_interpretation": (
                "No eligible governed Findings were available; this is not a clean bill of health."
                if status == "completed" and not opportunities
                else None
            ),
        }
        trust_summary: dict[str, object] = {
            "support_counts": dict(sorted(support_counts.items())),
            "completed_trust_available": completed_trust_exists,
            "unsupported_opportunities_omitted": True,
        }
        input_contract = {
            "scan_policy": [SCAN_POLICY_CODE, SCAN_POLICY_VERSION],
            "ranking_policy": [RANKING_POLICY_CODE, RANKING_POLICY_VERSION],
            "organization_id": organization_id,
            "context": context,
            "finding_universe_count": finding_total,
            "findings": provenance_findings,
            "candidate_limit": MAX_CANDIDATE_FINDINGS,
            "opportunity_limit": MAX_OPPORTUNITIES,
            "data_exists": data_exists,
            "completed_trust_exists": completed_trust_exists,
        }
        input_fingerprint = _hash(input_contract)
        request_fingerprint = _hash(
            {
                "organization_id": organization_id,
                "input_fingerprint": input_fingerprint,
                "scan_policy_version": SCAN_POLICY_VERSION,
                "ranking_policy_version": RANKING_POLICY_VERSION,
            }
        )
        provenance: dict[str, object] = {
            "organization_id": str(organization_id),
            "scan_policy_code": SCAN_POLICY_CODE,
            "scan_policy_version": SCAN_POLICY_VERSION,
            "ranking_policy_code": RANKING_POLICY_CODE,
            "ranking_policy_version": RANKING_POLICY_VERSION,
            "customer_context_hash": _hash(context),
            "findings": provenance_findings,
            "input_fingerprint": input_fingerprint,
        }
        result_contract = {
            "status": status,
            "opportunities": opportunities,
            "data_gaps": gaps,
            "data_coverage": data_coverage,
            "trust_readiness": trust_summary,
            "customer_context": context,
            "next_investigation": next_investigation,
            "provenance": provenance,
            "limitations": limitations,
        }
        result_hash = _hash(result_contract)
        provenance["output_content_hash"] = result_hash
        return ScanAssembly(
            input_fingerprint=input_fingerprint,
            request_fingerprint=request_fingerprint,
            status=status,
            candidate_finding_count=len(findings),
            opportunities=opportunities,
            data_gaps=gaps,
            data_coverage=data_coverage,
            trust_readiness=trust_summary,
            customer_context=context,
            next_investigation=next_investigation,
            provenance=provenance,
            limitations=limitations,
            result_content_hash=result_hash,
        )

    @staticmethod
    def _context(db: Session, organization: Organization) -> dict[str, object]:
        objectives = list(
            db.scalars(
                select(OrganizationObjective.objective_code)
                .where(OrganizationObjective.organization_id == organization.id)
                .order_by(OrganizationObjective.objective_code)
            )
        )
        challenges = list(
            db.scalars(
                select(OrganizationChallenge.challenge_code)
                .where(OrganizationChallenge.organization_id == organization.id)
                .order_by(OrganizationChallenge.challenge_code)
            )
        )
        systems = [
            {"system_code": code, "custom_label": label}
            for code, label in db.execute(
                select(OrganizationSystem.system_code, OrganizationSystem.custom_label)
                .where(OrganizationSystem.organization_id == organization.id)
                .order_by(OrganizationSystem.system_code, OrganizationSystem.custom_label)
            )
        ]
        return {
            "industry": organization.industry,
            "sub_industry": organization.sub_industry,
            "objectives": objectives,
            "challenges": challenges,
            "systems": systems,
            "ranking_influence": "none_v1",
        }

    def _load_related(
        self,
        db: Session,
        organization_id: UUID,
        findings: list[Finding],
    ) -> dict[str, object]:
        finding_ids = [finding.id for finding in findings]
        trust_ids = {
            finding.trust_assessment_id for finding in findings if finding.trust_assessment_id
        }
        readiness_ids = {
            finding.analytical_readiness_id
            for finding in findings
            if finding.analytical_readiness_id
        }
        execution_ids = {
            finding.source_execution_id for finding in findings if finding.source_execution_id
        }
        trusts = self._tenant_map(
            organization_id,
            db.scalars(select(TrustAssessment).where(TrustAssessment.id.in_(trust_ids))),
            "Trust assessment",
        )
        readiness = self._tenant_map(
            organization_id,
            db.scalars(
                select(AnalyticalReadinessDecision).where(
                    AnalyticalReadinessDecision.id.in_(readiness_ids)
                )
            ),
            "Readiness decision",
        )
        executions = self._tenant_map(
            organization_id,
            db.scalars(
                select(IntelligenceExecution).where(IntelligenceExecution.id.in_(execution_ids))
            ),
            "Intelligence execution",
        )
        all_bundles = list(
            db.scalars(
                select(FindingEvidenceBundle)
                .where(FindingEvidenceBundle.finding_id.in_(finding_ids))
                .order_by(
                    FindingEvidenceBundle.finding_id,
                    FindingEvidenceBundle.bundle_version.desc(),
                )
            )
        )
        bundles: dict[UUID, FindingEvidenceBundle] = {}
        for bundle in all_bundles:
            self._require_org(organization_id, bundle.organization_id, "Finding evidence bundle")
            bundles.setdefault(bundle.finding_id, bundle)
        bundle_ids = [bundle.id for bundle in bundles.values()]
        items_by_bundle: dict[UUID, list[FindingEvidenceItem]] = defaultdict(list)
        for item in db.scalars(
            select(FindingEvidenceItem)
            .where(FindingEvidenceItem.evidence_bundle_id.in_(bundle_ids))
            .order_by(FindingEvidenceItem.evidence_bundle_id, FindingEvidenceItem.sequence_number)
        ):
            self._require_org(organization_id, item.organization_id, "Finding evidence item")
            items_by_bundle[item.evidence_bundle_id].append(item)
        self._validate_evidence_references(db, organization_id, items_by_bundle)

        links = list(
            db.scalars(
                select(OpportunityFinding).where(OpportunityFinding.finding_id.in_(finding_ids))
            )
        )
        for link in links:
            self._require_org(organization_id, link.organization_id, "Opportunity finding link")
        opportunity_ids = {link.opportunity_id for link in links}
        opportunities = self._tenant_map(
            organization_id,
            db.scalars(
                select(RecoveryOpportunity).where(RecoveryOpportunity.id.in_(opportunity_ids))
            ),
            "Recovery opportunity",
        )
        calculations_by_opportunity: dict[UUID, list[EconomicCalculation]] = defaultdict(list)
        for calculation in db.scalars(
            select(EconomicCalculation)
            .where(EconomicCalculation.opportunity_id.in_(opportunity_ids))
            .order_by(EconomicCalculation.calculated_at.desc(), EconomicCalculation.id.desc())
        ):
            self._require_org(organization_id, calculation.organization_id, "Economic calculation")
            calculations_by_opportunity[calculation.opportunity_id].append(calculation)
        priorities_by_opportunity: dict[UUID, list[PrioritizationAssessment]] = defaultdict(list)
        for priority in db.scalars(
            select(PrioritizationAssessment)
            .where(PrioritizationAssessment.opportunity_id.in_(opportunity_ids))
            .order_by(
                PrioritizationAssessment.calculated_at.desc(),
                PrioritizationAssessment.id.desc(),
            )
        ):
            self._require_org(organization_id, priority.organization_id, "Prioritization")
            priorities_by_opportunity[priority.opportunity_id].append(priority)
        overlap_by_opportunity: dict[UUID, OpportunityOverlapMember] = {}
        for member in db.scalars(
            select(OpportunityOverlapMember).where(
                OpportunityOverlapMember.opportunity_id.in_(opportunity_ids)
            )
        ):
            self._require_org(organization_id, member.organization_id, "Opportunity overlap")
            overlap_by_opportunity[member.opportunity_id] = member

        rules_by_assessment: dict[UUID, list[TrustRuleResult]] = defaultdict(list)
        for rule in db.scalars(
            select(TrustRuleResult).where(TrustRuleResult.trust_assessment_id.in_(trust_ids))
        ):
            self._require_org(organization_id, rule.organization_id, "Trust rule result")
            rules_by_assessment[rule.trust_assessment_id].append(rule)
        return {
            "trusts": trusts,
            "readiness": readiness,
            "executions": executions,
            "bundles": bundles,
            "items_by_bundle": items_by_bundle,
            "links": links,
            "opportunities": opportunities,
            "calculations": calculations_by_opportunity,
            "priorities": priorities_by_opportunity,
            "overlaps": overlap_by_opportunity,
            "rules": rules_by_assessment,
        }

    @staticmethod
    def _tenant_map(
        organization_id: UUID,
        rows: Any,
        label: str,
    ) -> dict[UUID, Any]:
        result: dict[UUID, Any] = {}
        for row in rows:
            DirectionalValueScanService._require_org(organization_id, row.organization_id, label)
            result[row.id] = row
        return result

    @staticmethod
    def _require_org(organization_id: UUID, actual: UUID, label: str) -> None:
        if actual != organization_id:
            raise ValueScanServiceError(
                "CROSS_TENANT_REFERENCE",
                f"{label} is outside the organization boundary",
                404,
            )

    def _validate_evidence_references(
        self,
        db: Session,
        organization_id: UUID,
        items_by_bundle: dict[UUID, list[FindingEvidenceItem]],
    ) -> None:
        reference_models = {
            "source_system_id": SourceSystem,
            "ingestion_batch_id": IngestionBatch,
            "dataset_id": Dataset,
            "lineage_node_id": LineageNode,
            "raw_record_reference_id": RawRecordReference,
        }
        references: dict[type[Any], set[UUID]] = defaultdict(set)
        for items in items_by_bundle.values():
            for item in items:
                for attribute, model in reference_models.items():
                    identifier = getattr(item, attribute)
                    if identifier is not None:
                        references[model].add(identifier)
        valid: set[tuple[type[Any], UUID]] = set()
        for model, identifiers in references.items():
            for row in db.scalars(select(model).where(model.id.in_(identifiers))):
                self._require_org(organization_id, row.organization_id, "Evidence reference")
                valid.add(_reference_key(model, row.id))
        for model, identifiers in references.items():
            if any(_reference_key(model, identifier) not in valid for identifier in identifiers):
                raise ValueScanServiceError(
                    "EVIDENCE_REFERENCE_UNAVAILABLE",
                    "A governed evidence reference is unavailable",
                    422,
                )

    def _project_finding(
        self,
        db: Session,
        organization_id: UUID,
        finding: Finding,
        related: dict[str, object],
    ) -> tuple[dict[str, object] | None, list[dict[str, object]], dict[str, object]]:
        trusts: dict[UUID, TrustAssessment] = related["trusts"]  # type: ignore[assignment]
        readiness_rows: dict[UUID, AnalyticalReadinessDecision] = related["readiness"]  # type: ignore[assignment]
        executions: dict[UUID, IntelligenceExecution] = related["executions"]  # type: ignore[assignment]
        bundles: dict[UUID, FindingEvidenceBundle] = related["bundles"]  # type: ignore[assignment]
        items_by_bundle: dict[UUID, list[FindingEvidenceItem]] = related["items_by_bundle"]  # type: ignore[assignment]
        rules: dict[UUID, list[TrustRuleResult]] = related["rules"]  # type: ignore[assignment]

        trust = trusts.get(finding.trust_assessment_id) if finding.trust_assessment_id else None
        readiness = (
            readiness_rows.get(finding.analytical_readiness_id)
            if finding.analytical_readiness_id
            else None
        )
        execution = (
            executions.get(finding.source_execution_id) if finding.source_execution_id else None
        )
        bundle = bundles.get(finding.id)
        support_state = "SUPPORTED"
        gap_code: str | None = None
        gap_reason: str | None = None
        remediation: str | None = None

        if trust is None or readiness is None:
            support_state = "UNSUPPORTED"
            gap_code = "GOVERNED_READINESS_UNAVAILABLE"
            gap_reason = "The Finding lacks an available tenant-owned Trust/readiness decision."
        elif trust.status not in {
            TrustAssessmentStatus.COMPLETED.value,
            TrustAssessmentStatus.COMPLETED_WITH_WARNINGS.value,
        }:
            support_state = "STALE"
            gap_code = "TRUST_LIFECYCLE_STALE"
            gap_reason = "The governing Trust assessment is no longer completed."
        elif readiness.trust_assessment_id != trust.id:
            support_state = "STALE"
            gap_code = "READINESS_TRUST_MISMATCH"
            gap_reason = "The readiness decision no longer matches the governing Trust assessment."
        elif readiness.readiness_status in {
            ReadinessStatus.BLOCKED.value,
            ReadinessStatus.INSUFFICIENT_DATA.value,
        }:
            support_state = "UNSUPPORTED"
            gap_code = "ANALYSIS_NOT_READY"
            gap_reason = readiness.explanation
        elif readiness.readiness_status == ReadinessStatus.READY_WITH_WARNINGS.value:
            support_state = "PARTIAL"
        elif readiness.readiness_status != ReadinessStatus.READY.value:
            support_state = "UNSUPPORTED"
            gap_code = "ANALYSIS_NOT_READY"
            gap_reason = readiness.explanation

        if bundle is None:
            support_state = "UNSUPPORTED"
            gap_code = "FINDING_EVIDENCE_UNAVAILABLE"
            gap_reason = "A finalized Finding evidence bundle is unavailable."
        elif (
            bundle.status != "complete"
            or bundle.completeness_status != "complete"
            or bundle.finalized_at is None
        ):
            support_state = "STALE"
            gap_code = "FINDING_EVIDENCE_STALE"
            gap_reason = "The latest Finding evidence bundle is not complete and finalized."

        if execution is None or finding.source_result_id != finding.source_execution_id:
            support_state = "UNSUPPORTED"
            gap_code = "SOURCE_EXECUTION_UNAVAILABLE"
            gap_reason = "The governed source execution is unavailable."
        elif (
            execution.status != IntelligenceExecutionStatus.COMPLETED.value
            or execution.definition_code != finding.definition_code
            or execution.definition_version != finding.definition_version
            or execution.definition_fingerprint != finding.definition_fingerprint
            or execution.dataset_id != finding.dataset_id
            or execution.trust_assessment_id != finding.trust_assessment_id
            or execution.readiness_decision_id != finding.analytical_readiness_id
        ):
            support_state = "STALE"
            gap_code = "SOURCE_EXECUTION_STALE"
            gap_reason = "The Finding no longer matches its governed source execution."
        elif execution.dataset_version_id is None:
            support_state = "UNSUPPORTED"
            gap_code = "GOVERNED_PROVENANCE_UNAVAILABLE"
            gap_reason = "The source execution lacks an exact governed dataset version."
        else:
            try:
                governed_dataset_provenance_service.resolve(
                    db,
                    organization_id,
                    execution.dataset_id,
                    execution.dataset_version_id,
                )
            except GovernedProvenanceError as exc:
                support_state = "STALE"
                gap_code = "GOVERNED_PROVENANCE_STALE"
                gap_reason = str(exc)

        if finding.content_fingerprint is None:
            support_state = "UNSUPPORTED"
            gap_code = "FINDING_FINGERPRINT_UNAVAILABLE"
            gap_reason = "The Finding lacks an immutable content fingerprint."

        evidence_items = items_by_bundle.get(bundle.id, []) if bundle else []
        evidence_refs = [
            self._evidence_reference(item) for item in evidence_items[:MAX_EVIDENCE_REFERENCES]
        ]
        evidence_truncated = len(evidence_items) > MAX_EVIDENCE_REFERENCES
        if gap_code:
            remediation = self._remediation(
                rules.get(trust.id, []) if trust else [],
                readiness.blocking_rule_codes if readiness else [],
            )
            gap = self._finding_gap(
                finding,
                gap_code,
                support_state,
                gap_reason or "Governed analysis is not supportable.",
                remediation,
                trust,
                readiness,
                evidence_refs,
            )
            return (
                None,
                [gap],
                self._finding_provenance(
                    finding,
                    trust,
                    readiness,
                    execution,
                    bundle,
                    evidence_refs,
                    support_state,
                    None,
                    None,
                ),
            )

        assert trust is not None
        assert readiness is not None
        assert execution is not None
        assert bundle is not None
        selected_opportunity, calculation, priority, overlap = self._select_economics(
            finding, related
        )
        limitations = list(finding.limitations or [])
        warnings = list(finding.warnings or [])
        if readiness and readiness.warning_rule_codes:
            warnings.extend(readiness.warning_rule_codes)
        if evidence_truncated:
            limitations.append(
                f"Evidence references were bounded to {MAX_EVIDENCE_REFERENCES} items."
            )
        finding_currency = finding.exposure_currency
        economics_currency = calculation.currency_code if calculation else None
        if finding_currency and economics_currency and finding_currency != economics_currency:
            limitations.append(
                "Finding exposure and Economics use different currencies; values were not "
                "converted, reconciled, or aggregated."
            )

        potential_exposure = None
        if finding.exposure_value is not None:
            potential_exposure = {
                "truth_label": "POTENTIAL_EXPOSURE",
                "value": _value(finding.exposure_value),
                "value_type": finding.exposure_value_type,
                "currency": finding.exposure_currency,
                "source": "finding",
                "source_id": str(finding.id),
            }
        elif calculation is not None:
            potential_exposure = {
                "truth_label": "POTENTIAL_EXPOSURE",
                "gross_value": _value(calculation.gross_exposure),
                "addressable_value": _value(calculation.addressable_exposure),
                "currency": calculation.currency_code,
                "source": "economic_calculation",
                "source_id": str(calculation.id),
            }
        expected_recovery = (
            {
                "truth_label": "EXPECTED_RECOVERY",
                "expected_recoverable_value": _value(calculation.expected_recoverable_value),
                "probability_adjusted_value": _value(calculation.probability_adjusted_value),
                "currency": calculation.currency_code,
                "calculation_id": str(calculation.id),
                "calculation_version": calculation.calculation_version,
            }
            if calculation is not None
            else None
        )
        economics_gap: list[dict[str, object]] = []
        if calculation is None:
            economics_gap.append(
                self._finding_gap(
                    finding,
                    "AUTHORITATIVE_ECONOMICS_UNAVAILABLE",
                    "PARTIAL",
                    "The supported Finding has no authoritative expected-recovery calculation.",
                    (
                        "Complete a governed Recovery Economics assessment if monetary recovery "
                        "is required."
                    ),
                    trust,
                    readiness,
                    evidence_refs,
                )
            )

        investigation_code = (
            "REVIEW_AFFECTED_RECORDS"
            if any(item.evidence_type == "affected_record" for item in evidence_items)
            else "REVIEW_FINDING_EVIDENCE"
        )
        investigation_text = (
            f"Review the governed affected records for {finding.title}."
            if investigation_code == "REVIEW_AFFECTED_RECORDS"
            else f"Review the evidence and calculation trace for {finding.title}."
        )
        opportunity: dict[str, object] = {
            "rank": 0,
            "truth_label": "SUPPORTED_FINDING",
            "support_state": support_state,
            "finding_id": str(finding.id),
            "finding_code": finding.finding_code,
            "finding_status": finding.status,
            "title": finding.title,
            "finding_type": finding.finding_type,
            "domain": finding.domain_code,
            "process": finding.process_code,
            "finding_content_fingerprint": finding.content_fingerprint,
            "detected_at": (finding.detected_at or finding.created_at).isoformat(),
            "source_execution_id": str(finding.source_execution_id),
            "definition_code": finding.definition_code,
            "definition_version": finding.definition_version,
            "definition_fingerprint": finding.definition_fingerprint,
            "evidence_bundle": {
                "id": str(bundle.id),
                "version": bundle.bundle_version,
                "content_hash": bundle.content_hash,
            },
            "evidence_references": evidence_refs,
            "trust": {
                "assessment_id": str(trust.id),
                "status": trust.status,
                "readiness_id": str(readiness.id),
                "readiness_level": readiness.analytical_level,
                "readiness_status": readiness.readiness_status,
            },
            "observed_value": {
                "truth_label": "OBSERVED_VALUE",
                "value": _value(finding.measured_value),
                "value_type": finding.measured_value_type,
                "unit": finding.measured_unit,
                "currency": finding.measured_currency,
            },
            "potential_exposure": potential_exposure,
            "expected_recovery": expected_recovery,
            "confidence": {
                "level": finding.confidence_level,
                "score": _value(finding.confidence_score),
                "method_code": finding.confidence_method_code,
                "method_version": finding.confidence_method_version,
            },
            "severity": finding.severity,
            "materiality": finding.severity_reason,
            "priority_source": (
                "ECONOMICS_PRIORITIZATION"
                if priority is not None
                else "FINDING_PRIORITY"
                if finding.priority is not None
                else "UNRANKED"
            ),
            "priority_category": priority.priority_category if priority else None,
            "priority_score": _value(priority.priority_score) if priority else None,
            "finding_priority": finding.priority,
            "economics": {
                "opportunity_id": str(selected_opportunity.id) if selected_opportunity else None,
                "calculation_id": str(calculation.id) if calculation else None,
                "calculation_version": calculation.calculation_version if calculation else None,
                "prioritization_id": str(priority.id) if priority else None,
                "profile_code": priority.profile_code if priority else None,
                "model_name": priority.model_name if priority else None,
                "model_version": priority.model_version if priority else None,
                "overlap_inclusion_status": overlap.inclusion_status if overlap else "included",
                "overlap_allocation": _value(overlap.allocation_percentage) if overlap else "1",
            },
            "investigation": {
                "truth_label": "RECOMMENDATION",
                "code": investigation_code,
                "text": investigation_text,
            },
            "warnings": sorted(set(warnings)),
            "limitations": sorted(set(limitations)),
        }
        provenance = self._finding_provenance(
            finding,
            trust,
            readiness,
            execution,
            bundle,
            evidence_refs,
            support_state,
            calculation,
            priority,
        )
        return opportunity, economics_gap, provenance

    @staticmethod
    def _select_economics(
        finding: Finding,
        related: dict[str, object],
    ) -> tuple[
        RecoveryOpportunity | None,
        EconomicCalculation | None,
        PrioritizationAssessment | None,
        OpportunityOverlapMember | None,
    ]:
        links: list[OpportunityFinding] = related["links"]  # type: ignore[assignment]
        opportunities: dict[UUID, RecoveryOpportunity] = related["opportunities"]  # type: ignore[assignment]
        calculations: dict[UUID, list[EconomicCalculation]] = related["calculations"]  # type: ignore[assignment]
        priorities: dict[UUID, list[PrioritizationAssessment]] = related["priorities"]  # type: ignore[assignment]
        overlaps: dict[UUID, OpportunityOverlapMember] = related["overlaps"]  # type: ignore[assignment]
        candidates: list[
            tuple[
                RecoveryOpportunity,
                EconomicCalculation | None,
                PrioritizationAssessment | None,
                OpportunityOverlapMember | None,
            ]
        ] = []
        for link in links:
            if link.finding_id != finding.id:
                continue
            opportunity = opportunities.get(link.opportunity_id)
            if opportunity is None or opportunity.status not in ACTIVE_OPPORTUNITY_STATUSES:
                continue
            overlap = overlaps.get(opportunity.id)
            if overlap is not None and overlap.inclusion_status != "included":
                continue
            priority = priorities.get(opportunity.id, [None])[0]
            calculation = None
            if priority is not None:
                calculation = next(
                    (
                        item
                        for item in calculations.get(opportunity.id, [])
                        if item.id == priority.calculation_id
                    ),
                    None,
                )
            if calculation is None:
                calculation = next(iter(calculations.get(opportunity.id, [])), None)
            candidates.append((opportunity, calculation, priority, overlap))
        if not candidates:
            return None, None, None, None
        candidates.sort(
            key=lambda item: (
                -(item[2].priority_score if item[2] else Decimal("-1")),
                -_timestamp(item[2].calculated_at if item[2] else None),
                str(item[0].id),
            )
        )
        return candidates[0]

    @staticmethod
    def _ranking_key(opportunity: dict[str, object]) -> tuple[object, ...]:
        score = opportunity["priority_score"]
        if score is not None:
            return (0, -Decimal(str(score)), str(opportunity["finding_id"]))
        confidence = opportunity["confidence"]
        confidence_score = (
            Decimal(str(confidence["score"]))  # type: ignore[index]
            if confidence["score"] is not None  # type: ignore[index]
            else Decimal("-1")
        )
        return (
            1,
            int(str(opportunity["finding_priority"] or 2**31 - 1)),
            -SEVERITY_RANK.get(str(opportunity["severity"]), 0),
            -confidence_score,
            -_timestamp(datetime.fromisoformat(str(opportunity["detected_at"])))
            if opportunity.get("detected_at")
            else 0,
            str(opportunity["finding_id"]),
        )

    @staticmethod
    def _evidence_reference(item: FindingEvidenceItem) -> dict[str, object]:
        return {
            "id": str(item.id),
            "evidence_type": item.evidence_type,
            "reference_type": item.reference_type,
            "reference_id": item.reference_id,
            "reference_fingerprint": item.reference_fingerprint,
            "label": item.label,
        }

    @staticmethod
    def _remediation(rules: list[TrustRuleResult], blocking_codes: list[str]) -> str | None:
        for rule in sorted(rules, key=lambda row: row.rule_code):
            if rule.rule_code in blocking_codes and rule.remediation_guidance:
                return rule.remediation_guidance
        return None

    @staticmethod
    def _finding_gap(
        finding: Finding,
        code: str,
        support_state: str,
        reason: str,
        remediation: str | None,
        trust: TrustAssessment | None,
        readiness: AnalyticalReadinessDecision | None,
        evidence_refs: list[dict[str, object]],
    ) -> dict[str, object]:
        return {
            "gap_code": code,
            "affected_analysis": finding.definition_code,
            "finding_id": str(finding.id),
            "support_state": support_state,
            "trust_assessment_id": str(trust.id) if trust else None,
            "readiness_id": str(readiness.id) if readiness else None,
            "missing_input": code.lower(),
            "why_it_matters": reason,
            "unlocks": f"supported analysis for {finding.title}",
            "remediation_guidance": remediation,
            "priority": finding.priority,
            "references": evidence_refs,
            "limitations": [reason],
        }

    @staticmethod
    def _organization_gap(code: str, reason: str, remediation: str) -> dict[str, object]:
        return {
            "gap_code": code,
            "affected_analysis": SCAN_POLICY_CODE,
            "support_state": "UNSUPPORTED",
            "missing_input": code.lower(),
            "why_it_matters": reason,
            "unlocks": "governed Directional Value Scan analysis",
            "remediation_guidance": remediation,
            "priority": 1,
            "references": [],
            "limitations": [reason],
        }

    @staticmethod
    def _finding_provenance(
        finding: Finding,
        trust: TrustAssessment | None,
        readiness: AnalyticalReadinessDecision | None,
        execution: IntelligenceExecution | None,
        bundle: FindingEvidenceBundle | None,
        evidence_refs: list[dict[str, object]],
        support_state: str,
        calculation: EconomicCalculation | None,
        priority: PrioritizationAssessment | None,
    ) -> dict[str, object]:
        return {
            "finding_id": str(finding.id),
            "finding_status": finding.status,
            "finding_content_fingerprint": finding.content_fingerprint,
            "support_state": support_state,
            "source_execution_id": str(execution.id) if execution else None,
            "definition_code": finding.definition_code,
            "definition_version": finding.definition_version,
            "definition_fingerprint": finding.definition_fingerprint,
            "dataset_id": str(execution.dataset_id) if execution else None,
            "dataset_version_id": (
                str(execution.dataset_version_id)
                if execution and execution.dataset_version_id
                else None
            ),
            "trust_assessment_id": str(trust.id) if trust else None,
            "trust_status": trust.status if trust else None,
            "readiness_id": str(readiness.id) if readiness else None,
            "readiness_level": readiness.analytical_level if readiness else None,
            "readiness_status": readiness.readiness_status if readiness else None,
            "evidence_bundle_id": str(bundle.id) if bundle else None,
            "evidence_bundle_version": bundle.bundle_version if bundle else None,
            "evidence_bundle_hash": bundle.content_hash if bundle else None,
            "evidence_references": evidence_refs,
            "economic_calculation_id": str(calculation.id) if calculation else None,
            "economic_calculation_version": (
                calculation.calculation_version if calculation else None
            ),
            "economic_input_hash": _hash(calculation.input_snapshot) if calculation else None,
            "prioritization_id": str(priority.id) if priority else None,
            "priority_profile_code": priority.profile_code if priority else None,
            "priority_model_name": priority.model_name if priority else None,
            "priority_model_version": priority.model_version if priority else None,
        }

    @staticmethod
    def _opportunity_currencies(opportunity: dict[str, object]) -> set[str]:
        currencies: set[str] = set()
        for key in ("observed_value", "potential_exposure", "expected_recovery"):
            value = opportunity.get(key)
            if isinstance(value, dict) and value.get("currency"):
                currencies.add(str(value["currency"]))
        return currencies

    @staticmethod
    def _next_investigation(
        opportunities: list[dict[str, object]],
        gaps: list[dict[str, object]],
        status: str,
    ) -> dict[str, object] | None:
        if status != "refused" and opportunities:
            investigation = opportunities[0]["investigation"]
            return dict(investigation) if isinstance(investigation, dict) else None
        if gaps:
            gap = sorted(
                gaps,
                key=lambda item: (
                    int(str(item.get("priority") or 2**31 - 1)),
                    str(item["gap_code"]),
                ),
            )[0]
            return {
                "truth_label": "RECOMMENDATION",
                "code": "RESOLVE_BLOCKING_DATA_GAP",
                "text": gap.get("remediation_guidance")
                or "Resolve the highest-priority governed data gap.",
                "gap_code": gap["gap_code"],
            }
        return None


directional_value_scan_service = DirectionalValueScanService()
