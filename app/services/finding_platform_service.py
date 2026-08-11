from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.entities import (
    Finding,
    FindingGovernanceTier,
    FindingStatus,
    Organization,
    OrganizationStatus,
)
from app.models.findings import (
    FindingCalculationTrace,
    FindingEvidenceBundle,
    FindingEvidenceItem,
    FindingReview,
    FindingRuleTrace,
    FindingStatusHistory,
)
from app.models.ingestion import Dataset, IngestionBatch
from app.models.intelligence import IntelligenceExecution, IntelligenceExecutionStatus
from app.models.raw_lineage import LineageNode, RawRecordReference
from app.models.source_system import SourceSystem
from app.models.trust import (
    AnalyticalReadinessDecision,
    ReadinessStatus,
    TrustAssessment,
    TrustAssessmentStatus,
)
from app.registries.calculation_registry import (
    DefinitionNotFoundError as CalculationDefinitionNotFoundError,
)
from app.registries.calculation_registry import default_calculation_registry
from app.registries.rule_registry import (
    DefinitionNotFoundError as RuleDefinitionNotFoundError,
)
from app.registries.rule_registry import default_rule_registry
from app.schemas.findings import (
    CandidateFindingCreate,
    EvidenceItemCreate,
    FindingStatusValue,
    LifecycleCommand,
    ReviewCreate,
    ReviewDecision,
)


class FindingPlatformError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class FindingNotFoundError(FindingPlatformError):
    def __init__(self) -> None:
        super().__init__("FINDING_NOT_FOUND", "Finding not found")


def _hash(value: object) -> str:
    encoded = json.dumps(value, default=str, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


class FindingDeduplicationService:
    @staticmethod
    def key(
        organization_id: UUID,
        execution: IntelligenceExecution,
        payload: CandidateFindingCreate,
    ) -> str:
        affected_references = sorted(
            (
                item.reference_type,
                item.reference_id,
                item.canonical_record_reference,
            )
            for item in payload.evidence
            if item.evidence_type.value == "affected_record"
        )
        return _hash(
            {
                "organization_id": organization_id,
                "definition_code": execution.definition_code,
                "definition_version": execution.definition_version,
                "finding_type": payload.finding_type,
                "dataset_reference": payload.dataset_reference,
                "occurrence_start": payload.occurrence_start,
                "occurrence_end": payload.occurrence_end,
                "affected_references": affected_references,
                "measured_value_type": payload.measured_value_type,
                "measured_value": payload.measured_value,
                "measured_unit": payload.measured_unit,
                "measured_currency": payload.measured_currency,
            }
        )


class FindingPublicationService:
    def __init__(self) -> None:
        self.calculations = default_calculation_registry()
        self.rules = default_rule_registry()
        self.deduplication = FindingDeduplicationService()

    def publish_candidate_finding(
        self,
        db: Session,
        organization_id: UUID,
        payload: CandidateFindingCreate,
        actor_user_id: UUID,
    ) -> Finding:
        self._organization(db, organization_id)
        execution = self._execution(db, organization_id, payload.execution_id)
        definition_operation = self._definition_operation(execution)
        self._validate_execution_contract(db, organization_id, execution, payload)
        self._validate_measurement(execution, payload)
        self._validate_evidence_references(db, organization_id, payload.evidence)
        deduplication_key = self.deduplication.key(organization_id, execution, payload)
        existing = db.scalar(
            select(Finding).where(
                Finding.organization_id == organization_id,
                Finding.deduplication_key == deduplication_key,
            )
        )
        if existing is not None:
            return existing
        now = datetime.now(UTC)
        content = {
            "organization_id": organization_id,
            "execution_id": execution.id,
            "definition_code": execution.definition_code,
            "definition_version": execution.definition_version,
            "finding_type": payload.finding_type,
            "measured_value": payload.measured_value,
            "exposure_value": payload.exposure_value,
            "severity": payload.severity,
            "confidence_level": payload.confidence_level,
            "dataset_reference": payload.dataset_reference,
            "warnings": payload.warnings,
            "limitations": payload.limitations,
        }
        finding = Finding(
            organization_id=organization_id,
            governance_tier=FindingGovernanceTier.GOVERNED.value,
            rule_id=execution.definition_code,
            finding_code=f"FND-{deduplication_key[:16].upper()}",
            finding_type=payload.finding_type.value,
            title=payload.title,
            summary=payload.summary,
            description=payload.description,
            domain=payload.domain_code,
            domain_code=payload.domain_code,
            process_code=payload.process_code,
            industry_pack_code=payload.industry_pack_code,
            severity=payload.severity.value,
            severity_reason=dict(payload.severity_reason),
            priority=3,
            exposure_low=float(payload.exposure_value or 0),
            exposure_high=float(payload.exposure_value or 0),
            currency=payload.exposure_currency or payload.measured_currency or "",
            confidence_score=payload.confidence_score or Decimal("0"),
            confidence_level=payload.confidence_level.value,
            confidence_method_code=payload.confidence_method_code,
            confidence_method_version=payload.confidence_method_version,
            confidence_components=payload.confidence_components,
            confidence_interpretation=payload.confidence_interpretation,
            confidence_limitations=payload.confidence_limitations,
            status=FindingStatus.PUBLISHED.value,
            ontology_concept_ids=[],
            measured_value=payload.measured_value,
            measured_value_type=payload.measured_value_type.value,
            measured_unit=payload.measured_unit,
            measured_currency=payload.measured_currency,
            exposure_value=payload.exposure_value,
            exposure_value_type=(
                payload.exposure_value_type.value if payload.exposure_value_type else None
            ),
            exposure_currency=payload.exposure_currency,
            affected_record_count=payload.affected_record_count,
            occurrence_start=payload.occurrence_start,
            occurrence_end=payload.occurrence_end,
            detected_at=execution.evaluation_time,
            published_at=now,
            source_execution_id=execution.id,
            source_result_id=execution.id,
            definition_code=execution.definition_code,
            definition_version=execution.definition_version,
            definition_fingerprint=execution.definition_fingerprint,
            trust_assessment_id=execution.trust_assessment_id,
            analytical_readiness_id=execution.readiness_decision_id,
            dataset_id=execution.dataset_id,
            dataset_reference=payload.dataset_reference,
            warnings=payload.warnings,
            limitations=payload.limitations,
            content_fingerprint=_hash(content),
            deduplication_key=deduplication_key,
            created_by_user_id=actor_user_id,
            updated_by_user_id=actor_user_id,
            updated_at=now,
        )
        db.add(finding)
        db.flush()
        bundle = self._create_evidence(
            db, organization_id, finding, execution, payload, actor_user_id
        )
        self._create_traces(
            db,
            organization_id,
            finding,
            execution,
            payload,
            definition_operation,
        )
        bundle.content_hash = self._bundle_hash(execution, payload)
        bundle.status = "complete"
        bundle.completeness_status = "complete"
        bundle.finalized_at = now
        db.add(
            FindingStatusHistory(
                organization_id=organization_id,
                finding_id=finding.id,
                previous_status=FindingStatus.DRAFT.value,
                new_status=FindingStatus.PUBLISHED.value,
                reason_code="publication_policy_satisfied",
                changed_by_user_id=actor_user_id,
                changed_at=now,
                metadata_json={"execution_id": str(execution.id)},
            )
        )
        db.commit()
        db.refresh(finding)
        return finding

    @staticmethod
    def _organization(db: Session, organization_id: UUID) -> None:
        organization = db.scalar(
            select(Organization).where(
                Organization.id == organization_id,
                Organization.status == OrganizationStatus.ACTIVE.value,
            )
        )
        if organization is None:
            raise FindingPlatformError(
                "CROSS_TENANT_REFERENCE",
                "Active organization not found",
            )

    @staticmethod
    def _execution(db: Session, organization_id: UUID, execution_id: UUID) -> IntelligenceExecution:
        execution = db.scalar(
            select(IntelligenceExecution).where(
                IntelligenceExecution.id == execution_id,
                IntelligenceExecution.organization_id == organization_id,
            )
        )
        if execution is None:
            raise FindingPlatformError(
                "EXECUTION_NOT_ELIGIBLE",
                "Eligible execution not found",
            )
        if execution.status != IntelligenceExecutionStatus.COMPLETED.value:
            raise FindingPlatformError(
                "EXECUTION_NOT_ELIGIBLE",
                "Only completed executions may publish findings",
            )
        if execution.result_value is None:
            raise FindingPlatformError(
                "RESULT_NOT_ELIGIBLE",
                "Execution result is not eligible",
            )
        return execution

    def _definition_operation(self, execution: IntelligenceExecution) -> str:
        try:
            if execution.execution_type == "calculation":
                calculation_definition = self.calculations.get(
                    execution.definition_code,
                    execution.definition_version,
                )
                if calculation_definition.status != "active":
                    raise FindingPlatformError(
                        "DEFINITION_REFERENCE_INVALID",
                        "Definition is not eligible for publication",
                    )
                operation = calculation_definition.operation.value
            else:
                rule_definition = self.rules.get(
                    execution.definition_code,
                    execution.definition_version,
                )
                if rule_definition.status != "active":
                    raise FindingPlatformError(
                        "DEFINITION_REFERENCE_INVALID",
                        "Definition is not eligible for publication",
                    )
                operation = rule_definition.operator.value
        except (
            CalculationDefinitionNotFoundError,
            RuleDefinitionNotFoundError,
        ) as exc:
            raise FindingPlatformError(
                "DEFINITION_REFERENCE_INVALID",
                "Registered definition not found",
            ) from exc
        return operation

    @staticmethod
    def _validate_execution_contract(
        db: Session,
        organization_id: UUID,
        execution: IntelligenceExecution,
        payload: CandidateFindingCreate,
    ) -> None:
        if payload.result_id != execution.id:
            raise FindingPlatformError(
                "RESULT_NOT_ELIGIBLE",
                "Result reference is not eligible",
            )
        assessment = db.scalar(
            select(TrustAssessment).where(
                TrustAssessment.id == execution.trust_assessment_id,
                TrustAssessment.organization_id == organization_id,
                TrustAssessment.status.in_(
                    (
                        TrustAssessmentStatus.COMPLETED.value,
                        TrustAssessmentStatus.COMPLETED_WITH_WARNINGS.value,
                    )
                ),
            )
        )
        if assessment is None:
            raise FindingPlatformError(
                "TRUST_REFERENCE_INVALID",
                "Valid Trust assessment not found",
            )
        readiness = db.scalar(
            select(AnalyticalReadinessDecision).where(
                AnalyticalReadinessDecision.id == execution.readiness_decision_id,
                AnalyticalReadinessDecision.organization_id == organization_id,
                AnalyticalReadinessDecision.trust_assessment_id == assessment.id,
                AnalyticalReadinessDecision.readiness_status.in_(
                    (
                        ReadinessStatus.READY.value,
                        ReadinessStatus.READY_WITH_WARNINGS.value,
                    )
                ),
            )
        )
        if readiness is None:
            raise FindingPlatformError(
                "READINESS_REFERENCE_INVALID",
                "Valid readiness decision not found",
            )
        dataset = db.scalar(
            select(Dataset).where(
                Dataset.id == execution.dataset_id,
                Dataset.organization_id == organization_id,
            )
        )
        if dataset is None:
            raise FindingPlatformError(
                "CROSS_TENANT_REFERENCE",
                "Dataset reference is not eligible",
            )

    @staticmethod
    def _validate_measurement(
        execution: IntelligenceExecution,
        payload: CandidateFindingCreate,
    ) -> None:
        if payload.measured_value != execution.result_value:
            raise FindingPlatformError(
                "RESULT_NOT_ELIGIBLE",
                "Measured value must equal the immutable execution result",
            )
        if payload.measured_unit != execution.unit:
            raise FindingPlatformError(
                "INVALID_VALUE_UNIT",
                "Measured unit must match the execution result",
            )
        if payload.measured_currency != execution.currency:
            raise FindingPlatformError(
                "INVALID_CURRENCY",
                "Measured currency must match the execution result",
            )
        if payload.exposure_value != execution.exposure_value:
            raise FindingPlatformError(
                "INVALID_EXPOSURE",
                "Exposure must match the execution result",
            )
        if payload.exposure_currency != execution.exposure_currency:
            raise FindingPlatformError(
                "INVALID_CURRENCY",
                "Exposure currency must match the execution result",
            )

    @staticmethod
    def _validate_evidence_references(
        db: Session,
        organization_id: UUID,
        evidence: list[EvidenceItemCreate],
    ) -> None:
        model_by_field = (
            ("source_system_id", SourceSystem),
            ("ingestion_batch_id", IngestionBatch),
            ("dataset_id", Dataset),
            ("lineage_node_id", LineageNode),
            ("raw_record_reference_id", RawRecordReference),
        )
        for item in evidence:
            for field, model in model_by_field:
                reference_id = getattr(item, field)
                if reference_id is None:
                    continue
                exists = db.scalar(
                    select(model.id).where(
                        model.id == reference_id,
                        model.organization_id == organization_id,
                    )
                )
                if exists is None:
                    raise FindingPlatformError(
                        "CROSS_TENANT_REFERENCE",
                        "Evidence reference is not eligible",
                    )

    @staticmethod
    def _bundle_hash(
        execution: IntelligenceExecution,
        payload: CandidateFindingCreate,
    ) -> str:
        return _hash(
            {
                "execution_id": execution.id,
                "definition_fingerprint": execution.definition_fingerprint,
                "policy": (
                    payload.evidence_policy_code,
                    payload.evidence_policy_version,
                ),
                "evidence": [item.model_dump() for item in payload.evidence],
                "calculation_traces": [item.model_dump() for item in payload.calculation_traces],
                "rule_traces": [item.model_dump() for item in payload.rule_traces],
            }
        )

    def _create_evidence(
        self,
        db: Session,
        organization_id: UUID,
        finding: Finding,
        execution: IntelligenceExecution,
        payload: CandidateFindingCreate,
        actor_user_id: UUID,
    ) -> FindingEvidenceBundle:
        bundle = FindingEvidenceBundle(
            organization_id=organization_id,
            finding_id=finding.id,
            bundle_version=1,
            evidence_policy_code=payload.evidence_policy_code,
            evidence_policy_version=payload.evidence_policy_version,
            status="open",
            completeness_status="incomplete",
            content_hash="0" * 64,
            created_by_user_id=actor_user_id,
        )
        db.add(bundle)
        db.flush()
        mandatory = [
            ("execution", "intelligence_execution", str(execution.id), "Source execution"),
            (
                "oikb_definition",
                "definition",
                f"{execution.definition_code}@{execution.definition_version}",
                "Immutable OIKB definition",
            ),
            (
                "trust_assessment",
                "trust_assessment",
                str(execution.trust_assessment_id),
                "Trust assessment",
            ),
            (
                "readiness_decision",
                "readiness_decision",
                str(execution.readiness_decision_id),
                "Analytical readiness decision",
            ),
            ("dataset", "dataset", str(execution.dataset_id), "Source dataset"),
        ]
        sequence = 1
        for evidence_type, reference_type, reference_id, label in mandatory:
            db.add(
                FindingEvidenceItem(
                    organization_id=organization_id,
                    evidence_bundle_id=bundle.id,
                    evidence_type=evidence_type,
                    reference_type=reference_type,
                    reference_id=reference_id,
                    reference_fingerprint=execution.definition_fingerprint,
                    label=label,
                    dataset_id=(execution.dataset_id if evidence_type == "dataset" else None),
                    sequence_number=sequence,
                    metadata_json={},
                )
            )
            sequence += 1
        for item in payload.evidence:
            db.add(
                FindingEvidenceItem(
                    organization_id=organization_id,
                    evidence_bundle_id=bundle.id,
                    sequence_number=sequence,
                    metadata_json=dict(item.metadata),
                    **item.model_dump(exclude={"metadata"}),
                )
            )
            sequence += 1
        return bundle

    @staticmethod
    def _create_traces(
        db: Session,
        organization_id: UUID,
        finding: Finding,
        execution: IntelligenceExecution,
        payload: CandidateFindingCreate,
        definition_operation: str,
    ) -> None:
        for sequence, calculation_trace in enumerate(payload.calculation_traces, 1):
            trace_data = calculation_trace.model_dump()
            db.add(
                FindingCalculationTrace(
                    organization_id=organization_id,
                    finding_id=finding.id,
                    execution_id=execution.id,
                    definition_code=execution.definition_code,
                    definition_version=execution.definition_version,
                    engine_version=calculation_trace.engine_version,
                    operation_code=calculation_trace.operation_code or definition_operation,
                    sequence_number=sequence,
                    input_reference_summary=dict(calculation_trace.input_reference_summary),
                    parameter_summary=dict(calculation_trace.parameter_summary),
                    output_value=execution.result_value,
                    output_type=payload.measured_value_type.value,
                    output_unit=execution.unit,
                    output_currency=execution.currency,
                    warnings=calculation_trace.warnings,
                    content_hash=_hash(trace_data),
                )
            )
        for sequence, rule_trace in enumerate(payload.rule_traces, 1):
            trace_data = rule_trace.model_dump()
            db.add(
                FindingRuleTrace(
                    organization_id=organization_id,
                    finding_id=finding.id,
                    execution_id=execution.id,
                    rule_code=execution.definition_code,
                    rule_version=execution.definition_version,
                    condition_code=rule_trace.condition_code,
                    sequence_number=sequence,
                    evaluation_result=rule_trace.evaluation_result,
                    operand_reference_summary=dict(rule_trace.operand_reference_summary),
                    comparison_operator=rule_trace.comparison_operator,
                    threshold_summary=dict(rule_trace.threshold_summary),
                    warnings=rule_trace.warnings,
                    content_hash=_hash(trace_data),
                )
            )


class FindingQueryService:
    def get(self, db: Session, organization_id: UUID, finding_id: UUID) -> Finding:
        finding = db.scalar(
            select(Finding).where(
                Finding.id == finding_id,
                Finding.organization_id == organization_id,
                Finding.finding_code.is_not(None),
            )
        )
        if finding is None:
            raise FindingNotFoundError()
        return finding

    def list(
        self,
        db: Session,
        organization_id: UUID,
        *,
        page: int,
        page_size: int,
        status: str | None = None,
        finding_type: str | None = None,
        severity: str | None = None,
        domain: str | None = None,
        process: str | None = None,
        industry_pack: str | None = None,
        definition_code: str | None = None,
        detected_from: datetime | None = None,
        detected_to: datetime | None = None,
        occurrence_from: datetime | None = None,
        occurrence_to: datetime | None = None,
        minimum_exposure: Decimal | None = None,
        currency: str | None = None,
        review_state: str | None = None,
        governance_tier: str | None = None,
    ) -> tuple[list[Finding], int]:
        filters = [
            Finding.organization_id == organization_id,
            Finding.finding_code.is_not(None),
        ]
        if status is None:
            filters.append(Finding.status != FindingStatus.ARCHIVED.value)
        else:
            filters.append(Finding.status == status)
        if governance_tier is None:
            filters.append(Finding.governance_tier == FindingGovernanceTier.GOVERNED.value)
        else:
            filters.append(Finding.governance_tier == governance_tier)
        for value, column in (
            (finding_type, Finding.finding_type),
            (severity, Finding.severity),
            (domain, Finding.domain_code),
            (process, Finding.process_code),
            (industry_pack, Finding.industry_pack_code),
            (definition_code, Finding.definition_code),
            (currency, Finding.exposure_currency),
        ):
            if value is not None:
                filters.append(column == value)
        if detected_from:
            filters.append(Finding.detected_at >= detected_from)
        if detected_to:
            filters.append(Finding.detected_at <= detected_to)
        if occurrence_from:
            filters.append(Finding.occurrence_start >= occurrence_from)
        if occurrence_to:
            filters.append(Finding.occurrence_end <= occurrence_to)
        if minimum_exposure is not None:
            filters.append(Finding.exposure_value >= minimum_exposure)
        if review_state is not None:
            filters.append(
                Finding.id.in_(
                    select(FindingReview.finding_id).where(
                        FindingReview.organization_id == organization_id,
                        FindingReview.review_status == review_state,
                    )
                )
            )
        total = db.scalar(select(func.count(Finding.id)).where(*filters)) or 0
        items = list(
            db.scalars(
                select(Finding)
                .where(*filters)
                .order_by(Finding.detected_at.desc(), Finding.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        return items, total


class FindingEvidenceService:
    def __init__(self) -> None:
        self.query = FindingQueryService()

    def get(
        self, db: Session, organization_id: UUID, finding_id: UUID
    ) -> tuple[FindingEvidenceBundle, list[FindingEvidenceItem]]:
        self.query.get(db, organization_id, finding_id)
        bundle = db.scalar(
            select(FindingEvidenceBundle)
            .where(
                FindingEvidenceBundle.organization_id == organization_id,
                FindingEvidenceBundle.finding_id == finding_id,
            )
            .order_by(FindingEvidenceBundle.bundle_version.desc())
            .limit(1)
        )
        if bundle is None:
            raise FindingPlatformError(
                "EVIDENCE_INCOMPLETE",
                "Evidence bundle not found",
            )
        items = list(
            db.scalars(
                select(FindingEvidenceItem)
                .where(
                    FindingEvidenceItem.organization_id == organization_id,
                    FindingEvidenceItem.evidence_bundle_id == bundle.id,
                )
                .order_by(FindingEvidenceItem.sequence_number)
            ).all()
        )
        return bundle, items

    def calculation_traces(
        self, db: Session, organization_id: UUID, finding_id: UUID
    ) -> list[FindingCalculationTrace]:
        self.query.get(db, organization_id, finding_id)
        return list(
            db.scalars(
                select(FindingCalculationTrace)
                .where(
                    FindingCalculationTrace.organization_id == organization_id,
                    FindingCalculationTrace.finding_id == finding_id,
                )
                .order_by(FindingCalculationTrace.sequence_number)
            ).all()
        )

    def rule_traces(
        self, db: Session, organization_id: UUID, finding_id: UUID
    ) -> list[FindingRuleTrace]:
        self.query.get(db, organization_id, finding_id)
        return list(
            db.scalars(
                select(FindingRuleTrace)
                .where(
                    FindingRuleTrace.organization_id == organization_id,
                    FindingRuleTrace.finding_id == finding_id,
                )
                .order_by(FindingRuleTrace.sequence_number)
            ).all()
        )


class FindingLifecycleService:
    transitions = {
        FindingStatus.DRAFT.value: {FindingStatus.PUBLISHED.value},
        FindingStatus.PUBLISHED.value: {
            FindingStatus.UNDER_REVIEW.value,
            FindingStatus.DISMISSED.value,
            FindingStatus.SUPERSEDED.value,
            FindingStatus.RESOLVED.value,
            FindingStatus.ARCHIVED.value,
        },
        FindingStatus.UNDER_REVIEW.value: {
            FindingStatus.CONFIRMED.value,
            FindingStatus.DISMISSED.value,
        },
        FindingStatus.CONFIRMED.value: {
            FindingStatus.RESOLVED.value,
            FindingStatus.SUPERSEDED.value,
            FindingStatus.ARCHIVED.value,
        },
        FindingStatus.DISMISSED.value: {FindingStatus.ARCHIVED.value},
        FindingStatus.SUPERSEDED.value: {FindingStatus.ARCHIVED.value},
        FindingStatus.RESOLVED.value: {FindingStatus.ARCHIVED.value},
    }

    def __init__(self) -> None:
        self.query = FindingQueryService()

    def transition(
        self,
        db: Session,
        organization_id: UUID,
        finding_id: UUID,
        new_status: FindingStatusValue,
        command: LifecycleCommand,
        actor_user_id: UUID,
    ) -> Finding:
        finding = self.query.get(db, organization_id, finding_id)
        if new_status.value not in self.transitions.get(finding.status, set()):
            raise FindingPlatformError(
                "INVALID_STATUS_TRANSITION",
                "Invalid finding status transition",
            )
        previous = finding.status
        now = datetime.now(UTC)
        if new_status == FindingStatusValue.SUPERSEDED:
            replacement_id = command.superseding_finding_id
            if replacement_id is None or replacement_id == finding.id:
                raise FindingPlatformError(
                    "INVALID_STATUS_TRANSITION",
                    "A distinct superseding finding is required",
                )
            self.query.get(db, organization_id, replacement_id)
            finding.superseded_by_finding_id = replacement_id
            finding.superseded_at = now
        timestamp_field = {
            FindingStatusValue.CONFIRMED: "confirmed_at",
            FindingStatusValue.DISMISSED: "dismissed_at",
            FindingStatusValue.RESOLVED: "resolved_at",
            FindingStatusValue.ARCHIVED: "archived_at",
            FindingStatusValue.PUBLISHED: "published_at",
        }.get(new_status)
        if timestamp_field:
            setattr(finding, timestamp_field, now)
        finding.status = new_status.value
        finding.updated_at = now
        finding.updated_by_user_id = actor_user_id
        db.add(
            FindingStatusHistory(
                organization_id=organization_id,
                finding_id=finding.id,
                previous_status=previous,
                new_status=new_status.value,
                reason_code=command.reason_code,
                changed_by_user_id=actor_user_id,
                changed_at=now,
                metadata_json={
                    "superseding_finding_id": (
                        str(command.superseding_finding_id)
                        if command.superseding_finding_id
                        else None
                    )
                },
            )
        )
        db.commit()
        db.refresh(finding)
        return finding

    def history(
        self, db: Session, organization_id: UUID, finding_id: UUID
    ) -> list[FindingStatusHistory]:
        self.query.get(db, organization_id, finding_id)
        return list(
            db.scalars(
                select(FindingStatusHistory)
                .where(
                    FindingStatusHistory.organization_id == organization_id,
                    FindingStatusHistory.finding_id == finding_id,
                )
                .order_by(
                    FindingStatusHistory.changed_at,
                    case(
                        (FindingStatusHistory.new_status == "published", 1),
                        (FindingStatusHistory.new_status == "under_review", 2),
                        (FindingStatusHistory.new_status == "confirmed", 3),
                        (FindingStatusHistory.new_status == "dismissed", 3),
                        (FindingStatusHistory.new_status == "resolved", 4),
                        (FindingStatusHistory.new_status == "superseded", 4),
                        (FindingStatusHistory.new_status == "archived", 5),
                        else_=99,
                    ),
                    FindingStatusHistory.id,
                )
            ).all()
        )


class FindingReviewService:
    def __init__(self) -> None:
        self.query = FindingQueryService()
        self.lifecycle = FindingLifecycleService()

    def create(
        self,
        db: Session,
        organization_id: UUID,
        finding_id: UUID,
        payload: ReviewCreate,
        reviewer_user_id: UUID,
        reviewer_role: str,
    ) -> FindingReview:
        finding = self.query.get(db, organization_id, finding_id)
        if payload.decision == ReviewDecision.RETURN_TO_DRAFT:
            raise FindingPlatformError(
                "INVALID_STATUS_TRANSITION",
                "Published findings cannot return to draft",
            )
        if payload.decision == ReviewDecision.MARK_SUPERSEDED:
            self.lifecycle.transition(
                db,
                organization_id,
                finding_id,
                FindingStatusValue.SUPERSEDED,
                LifecycleCommand(
                    reason_code=payload.reason_code,
                    superseding_finding_id=payload.superseding_finding_id,
                ),
                reviewer_user_id,
            )
        else:
            target = {
                ReviewDecision.CONFIRM: FindingStatusValue.CONFIRMED,
                ReviewDecision.DISMISS: FindingStatusValue.DISMISSED,
                ReviewDecision.REQUEST_MORE_EVIDENCE: FindingStatusValue.UNDER_REVIEW,
            }[payload.decision]
            if (
                target
                in {
                    FindingStatusValue.CONFIRMED,
                    FindingStatusValue.DISMISSED,
                }
                and finding.status == FindingStatus.PUBLISHED.value
            ):
                self.lifecycle.transition(
                    db,
                    organization_id,
                    finding_id,
                    FindingStatusValue.UNDER_REVIEW,
                    LifecycleCommand(reason_code="review_started"),
                    reviewer_user_id,
                )
            self.lifecycle.transition(
                db,
                organization_id,
                finding_id,
                target,
                LifecycleCommand(reason_code=payload.reason_code),
                reviewer_user_id,
            )
        review = FindingReview(
            organization_id=organization_id,
            finding_id=finding_id,
            review_status="completed",
            decision=payload.decision.value,
            reviewer_user_id=reviewer_user_id,
            reviewer_role=reviewer_role,
            reason_code=payload.reason_code,
            comments=payload.comments,
            reviewed_at=datetime.now(UTC),
        )
        db.add(review)
        db.commit()
        db.refresh(review)
        return review

    def list(self, db: Session, organization_id: UUID, finding_id: UUID) -> list[FindingReview]:
        self.query.get(db, organization_id, finding_id)
        return list(
            db.scalars(
                select(FindingReview)
                .where(
                    FindingReview.organization_id == organization_id,
                    FindingReview.finding_id == finding_id,
                )
                .order_by(FindingReview.reviewed_at, FindingReview.id)
            ).all()
        )


finding_publication_service = FindingPublicationService()
finding_query_service = FindingQueryService()
finding_evidence_service = FindingEvidenceService()
finding_lifecycle_service = FindingLifecycleService()
finding_review_service = FindingReviewService()
