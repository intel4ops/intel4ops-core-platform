from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.ground_truth_validation.adapters.base import GroundTruthFormatError
from app.ground_truth_validation.adapters.registry import (
    AdapterSelectionError,
    default_ground_truth_package_adapter_registry,
)
from app.ground_truth_validation.causal_matcher import score_causal
from app.ground_truth_validation.dq_matcher import score_data_quality
from app.ground_truth_validation.integrity import validate_package_integrity
from app.ground_truth_validation.leakage_matcher import match_leakage
from app.ground_truth_validation.leakage_matcher import score_leakage as compute_leakage_score
from app.ground_truth_validation.matcher import match_findings
from app.ground_truth_validation.matcher import score as compute_finding_score
from app.ground_truth_validation.ontology import NormalizedPackage
from app.ground_truth_validation.repository import validation_ground_truth_repository
from app.ground_truth_validation.storage import write_ground_truth
from app.models.analysis_case import (
    AnalysisCase,
    AnalysisCaseDataset,
    AnalysisCaseRun,
    FindingSourceDataset,
)
from app.models.ground_truth_validation import (
    SimulationValidationRun,
    SimulationValidationRunStatus,
    ValidationCausalTruth,
    ValidationDataQualityTruth,
    ValidationDimensionCode,
    ValidationDimensionResult,
    ValidationDimensionStatus,
    ValidationExpectedFinding,
    ValidationFindingMatch,
    ValidationGroundTruth,
    ValidationGroundTruthDocument,
    ValidationIntegritySeverity,
    ValidationLeakageTruth,
    ValidationPackageIntegrityIssue,
    ValidationScore,
    ValidationSimulation,
)
from app.storage.base import StorageBackend
from app.storage.local_storage import LocalFileStorage

# Terminal AnalysisCaseRun statuses -- validation may only run against a
# run that has stopped changing. Kept in sync with
# app.models.analysis_case.AnalysisCaseRunStatus by the tests, not by a
# shared import of orchestration internals.
_TERMINAL_RUN_STATUSES = frozenset(
    {"interrupted", "review_required", "partial", "completed", "failed", "cancelled"}
)


class ValidationServiceError(ValueError):
    def __init__(self, message: str, *, code: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


def _default_storage() -> StorageBackend:
    return LocalFileStorage(get_settings().storage_root)


def _json_default(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"not JSON serializable: {value!r}")


class ValidationService:
    """Orchestrates the Validation Plane. Reads persisted operational
    results (Finding, AnalysisCaseRun, AnalysisCaseFinding,
    FindingSourceDataset, AnalysisCaseDataset) read-only, after a run has
    reached a terminal state -- never writes to any of them. Ground truth
    is read only through ValidationGroundTruthRepository."""

    def __init__(self, storage: StorageBackend | None = None) -> None:
        self.storage = storage or _default_storage()

    def create_simulation(
        self,
        db: Session,
        organization_id: UUID,
        simulation_code: str,
        name: str,
        analysis_case_id: UUID,
        actor_user_id: UUID,
    ) -> ValidationSimulation:
        case = db.scalar(
            select(AnalysisCase).where(
                AnalysisCase.organization_id == organization_id, AnalysisCase.id == analysis_case_id
            )
        )
        if case is None:
            raise ValidationServiceError(
                "AnalysisCase not found", code="case_not_found", status=404
            )
        existing = validation_ground_truth_repository.get_simulation_by_code(
            db, organization_id, simulation_code
        )
        if existing is not None:
            raise ValidationServiceError(
                f"simulation_code {simulation_code!r} already exists",
                code="simulation_code_conflict",
                status=409,
            )
        simulation = ValidationSimulation(
            organization_id=organization_id,
            simulation_code=simulation_code,
            name=name,
            analysis_case_id=analysis_case_id,
            created_by_user_id=actor_user_id,
        )
        db.add(simulation)
        db.commit()
        db.refresh(simulation)
        return simulation

    def upload_ground_truth(
        self,
        db: Session,
        organization_id: UUID,
        simulation_id: UUID,
        payload: dict[str, object],
        actor_user_id: UUID,
    ) -> ValidationGroundTruth:
        """Accepts either the V1 simple {expected_findings, ...} shape or a
        V2 package {schema_version, manifest, documents: {role: content}}
        -- the adapter registry (section 4) decides which, never this
        method. New schemas are new adapters, not new branches here."""
        simulation = validation_ground_truth_repository.get_simulation(
            db, organization_id, simulation_id
        )
        if simulation is None:
            raise ValidationServiceError(
                "Simulation not found", code="simulation_not_found", status=404
            )

        source_schema_version = payload.get("schema_version")
        package_metadata = {
            "schema_version": source_schema_version,
            "manifest": payload.get("manifest"),
            "documents": payload.get("documents"),
            "expected_findings": payload.get("expected_findings"),
        }
        selection = default_ground_truth_package_adapter_registry.select_for_package(
            package_metadata
        )
        if selection.adapter is None:
            if selection.error == AdapterSelectionError.UNKNOWN_SCHEMA_VERSION:
                supported = ", ".join(selection.supported_schema_versions)
                raise ValidationServiceError(
                    f"schema_version {source_schema_version!r} is not a recognized ground-truth "
                    f"package schema. Supported: {supported}",
                    code="unknown_package_schema_version",
                )
            if selection.error == AdapterSelectionError.AMBIGUOUS:
                candidates = ", ".join(selection.candidate_codes)
                raise ValidationServiceError(
                    "More than one ground-truth package adapter recognizes this payload shape "
                    f"({candidates}). Declare an explicit schema_version to disambiguate.",
                    code="ambiguous_package_schema",
                )
            raise ValidationServiceError(
                "No registered ground-truth package adapter recognizes this payload shape",
                code="unrecognized_package_schema",
            )
        adapter = selection.adapter
        try:
            normalized = adapter.normalize(payload)
        except GroundTruthFormatError as exc:
            raise ValidationServiceError(str(exc), code="ground_truth_format_error") from exc

        issues = validate_package_integrity(normalized)
        blocking = [i for i in issues if i.severity == ValidationIntegritySeverity.ERROR.value]
        if blocking:
            detail = "; ".join(f"{i.code}: {i.message}" for i in blocking[:5])
            raise ValidationServiceError(
                f"{len(blocking)} package integrity error(s) block this upload: {detail}",
                code="package_integrity_error",
            )

        previous = validation_ground_truth_repository.latest_ground_truth(
            db, organization_id, simulation_id
        )
        version = (previous.version + 1) if previous is not None else 1

        raw_bytes = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        checksum = hashlib.sha256(raw_bytes).hexdigest()
        write_result = write_ground_truth(
            self.storage, organization_id, simulation_id, version, raw_bytes
        )

        manifest_summary = None
        if normalized.manifest is not None:
            manifest_summary = asdict(normalized.manifest)

        ground_truth = ValidationGroundTruth(
            organization_id=organization_id,
            simulation_id=simulation_id,
            version=version,
            storage_reference=write_result.reference,
            checksum=checksum,
            expected_clean_areas=normalized.expected_clean_areas,
            tolerance=normalized.tolerance,
            adapter_code=normalized.adapter_code,
            adapter_version=normalized.adapter_version,
            schema_version=normalized.schema_version,
            source_schema_version=(
                source_schema_version if isinstance(source_schema_version, str) else None
            ),
            manifest_summary=manifest_summary,
            uploaded_by_user_id=actor_user_id,
        )
        db.add(ground_truth)
        db.flush()

        self._persist_documents(db, organization_id, ground_truth.id, payload, normalized)

        for expected in normalized.expected_findings:
            db.add(
                ValidationExpectedFinding(
                    organization_id=organization_id,
                    ground_truth_id=ground_truth.id,
                    expected_finding_code=expected.truth_finding_id,
                    domain=expected.domain,
                    severity=expected.severity,
                    entities=expected.entities,
                    evidence_refs=expected.evidence_refs,
                    expected_economic_impact=expected.expected_economic_impact,
                    currency=expected.currency,
                    description=expected.description,
                    expected_detection_family=expected.expected_detection_family,
                    linked_leakage_id=expected.linked_leakage_id,
                    affected_records=expected.affected_records or None,
                )
            )
        for leakage in normalized.leakage_truth:
            db.add(
                ValidationLeakageTruth(
                    organization_id=organization_id,
                    ground_truth_id=ground_truth.id,
                    truth_leakage_id=leakage.truth_leakage_id,
                    scenario_code=leakage.scenario_code,
                    business_context=leakage.business_context,
                    affected_records=leakage.affected_records or None,
                    entities=leakage.entities,
                    time_window=leakage.time_window,
                    root_cause=leakage.root_cause,
                    causal_chain=leakage.causal_chain or None,
                    severity=leakage.severity,
                    recoverable=leakage.recoverable,
                    detection_family=leakage.detection_family,
                    expected_evidence=leakage.expected_evidence,
                    true_leakage_value=leakage.true_leakage_value,
                    recoverable_value=leakage.recoverable_value,
                    currency=leakage.currency,
                    metadata_json=leakage.metadata,
                )
            )
        for causal in normalized.causal_truth:
            db.add(
                ValidationCausalTruth(
                    organization_id=organization_id,
                    ground_truth_id=ground_truth.id,
                    truth_causal_id=causal.truth_causal_id,
                    linked_leakage_id=causal.linked_leakage_id,
                    linked_finding_id=causal.linked_finding_id,
                    scenario_code=causal.scenario_code,
                    expected_root_cause=causal.expected_root_cause,
                    expected_causal_chain=causal.expected_causal_chain or None,
                    metadata_json=causal.metadata,
                )
            )
        for dq in normalized.data_quality_truth:
            db.add(
                ValidationDataQualityTruth(
                    organization_id=organization_id,
                    ground_truth_id=ground_truth.id,
                    truth_dq_id=dq.truth_dq_id,
                    dq_family=dq.dq_family,
                    affected_record=dq.affected_record,
                    affected_dataset_or_field=dq.affected_dataset_or_field,
                    detail=dq.detail,
                    severity=dq.severity,
                    metadata_json=dq.metadata,
                )
            )
        for issue in issues:  # only non-blocking (warning) issues remain here
            db.add(
                ValidationPackageIntegrityIssue(
                    organization_id=organization_id,
                    ground_truth_id=ground_truth.id,
                    severity=issue.severity,
                    code=issue.code,
                    message=issue.message,
                    document_role=issue.document_role,
                    truth_ref=issue.truth_ref,
                )
            )

        db.commit()
        db.refresh(ground_truth)
        return ground_truth

    def _persist_documents(
        self,
        db: Session,
        organization_id: UUID,
        ground_truth_id: UUID,
        payload: dict[str, object],
        normalized: NormalizedPackage,
    ) -> None:
        documents = payload.get("documents")
        roles: dict[str, object] = documents if isinstance(documents, dict) else {}
        if payload.get("manifest") is not None:
            roles = {**roles, "manifest": payload["manifest"]}
        if not roles and "expected_findings" in payload:
            roles = {"expected_findings": payload["expected_findings"]}
        for role, content in roles.items():
            content_bytes = json.dumps(content, sort_keys=True, default=str).encode("utf-8")
            record_count = len(content) if isinstance(content, (list, dict)) else None
            db.add(
                ValidationGroundTruthDocument(
                    organization_id=organization_id,
                    ground_truth_id=ground_truth_id,
                    declared_role=role,
                    detected_role=role,
                    storage_reference=f"{normalized.adapter_code}#{role}",
                    checksum=hashlib.sha256(content_bytes).hexdigest(),
                    record_count=record_count,
                )
            )

    def get_simulation(
        self, db: Session, organization_id: UUID, simulation_id: UUID
    ) -> ValidationSimulation:
        simulation = validation_ground_truth_repository.get_simulation(
            db, organization_id, simulation_id
        )
        if simulation is None:
            raise ValidationServiceError(
                "Simulation not found", code="simulation_not_found", status=404
            )
        return simulation

    def get_simulation_by_code(
        self, db: Session, organization_id: UUID, simulation_code: str
    ) -> ValidationSimulation:
        """P3.xxV.1: `simulation_code` is unique per organization (enforced
        at create_simulation()) but was previously only look-up-able by the
        opaque UUID a caller happened to already have from the create
        response -- there was no way to re-discover an existing
        registration's id from its human-meaningful code. Needed to safely
        register external Simulation Factory packages without risking a
        duplicate/orphaned registration on a re-run."""
        simulation = validation_ground_truth_repository.get_simulation_by_code(
            db, organization_id, simulation_code
        )
        if simulation is None:
            raise ValidationServiceError(
                "Simulation not found", code="simulation_not_found", status=404
            )
        return simulation

    def list_ground_truth_versions(
        self, db: Session, organization_id: UUID, simulation_id: UUID
    ) -> list[ValidationGroundTruth]:
        return list(
            db.scalars(
                select(ValidationGroundTruth)
                .where(
                    ValidationGroundTruth.organization_id == organization_id,
                    ValidationGroundTruth.simulation_id == simulation_id,
                )
                .order_by(ValidationGroundTruth.version.asc())
            ).all()
        )

    def validate_run(
        self,
        db: Session,
        organization_id: UUID,
        simulation_id: UUID,
        analysis_case_run_id: UUID,
        actor_user_id: UUID,
    ) -> tuple[
        SimulationValidationRun,
        ValidationScore,
        list[ValidationDimensionResult],
        list[ValidationFindingMatch],
    ]:
        # Local import: analysis_case_command_service is the PRODUCTION
        # read path this module deliberately depends on (the one allowed
        # direction -- Validation reads Operational, never the reverse).
        from app.services.analysis_case_command_service import analysis_case_command_service

        simulation = self.get_simulation(db, organization_id, simulation_id)
        ground_truth = validation_ground_truth_repository.latest_ground_truth(
            db, organization_id, simulation_id
        )
        if ground_truth is None:
            raise ValidationServiceError(
                "No ground truth uploaded for this simulation",
                code="ground_truth_missing",
                status=409,
            )

        run = db.scalar(
            select(AnalysisCaseRun).where(
                AnalysisCaseRun.organization_id == organization_id,
                AnalysisCaseRun.id == analysis_case_run_id,
                AnalysisCaseRun.analysis_case_id == simulation.analysis_case_id,
            )
        )
        if run is None:
            raise ValidationServiceError(
                "AnalysisCaseRun not found for this simulation's case",
                code="run_not_found",
                status=404,
            )
        if run.status not in _TERMINAL_RUN_STATUSES:
            raise ValidationServiceError(
                f"AnalysisCaseRun has not reached a terminal state (status={run.status!r})",
                code="run_not_terminal",
                status=409,
            )

        expected_findings = validation_ground_truth_repository.list_expected_findings(
            db, organization_id, ground_truth.id
        )
        leakage_truth = validation_ground_truth_repository.list_leakage_truth(
            db, organization_id, ground_truth.id
        )
        causal_truth = validation_ground_truth_repository.list_causal_truth(
            db, organization_id, ground_truth.id
        )
        dq_truth = validation_ground_truth_repository.list_data_quality_truth(
            db, organization_id, ground_truth.id
        )
        actual_findings = analysis_case_command_service.priorities(
            db, organization_id, simulation.analysis_case_id, run_id=run.id
        )

        source_labels_by_finding_id: dict[UUID, list[str]] = defaultdict(list)
        if actual_findings:
            finding_ids = [f.finding.id for f in actual_findings]
            rows = db.execute(
                select(FindingSourceDataset.finding_id, AnalysisCaseDataset.source_label)
                .join(
                    AnalysisCaseDataset,
                    AnalysisCaseDataset.dataset_id == FindingSourceDataset.dataset_id,
                )
                .where(
                    FindingSourceDataset.organization_id == organization_id,
                    FindingSourceDataset.finding_id.in_(finding_ids),
                    AnalysisCaseDataset.analysis_case_id == simulation.analysis_case_id,
                )
            ).all()
            for finding_id, source_label in rows:
                source_labels_by_finding_id[finding_id].append(source_label)

        validation_run = SimulationValidationRun(
            organization_id=organization_id,
            simulation_id=simulation_id,
            ground_truth_id=ground_truth.id,
            analysis_case_run_id=run.id,
            status=SimulationValidationRunStatus.PENDING.value,
            triggered_by_user_id=actor_user_id,
        )
        db.add(validation_run)
        db.flush()

        dimension_results: list[ValidationDimensionResult] = []

        # A. Finding detection (always attempted; NOT_AVAILABLE only if no
        # expected findings were ever uploaded for this ground truth).
        finding_pairs = match_findings(
            expected_findings, actual_findings, dict(source_labels_by_finding_id)
        )
        for pair in finding_pairs:
            db.add(
                ValidationFindingMatch(
                    organization_id=organization_id,
                    validation_run_id=validation_run.id,
                    dimension_code=ValidationDimensionCode.FINDING_DETECTION.value,
                    match_type=pair.match_type,
                    expected_finding_id=(pair.expected.id if pair.expected else None),
                    actual_finding_id=(pair.actual.finding.id if pair.actual else None),
                    severity_match=pair.severity_match,
                    entity_match=pair.entity_match,
                    evidence_match=pair.evidence_match,
                    economic_variance_pct=pair.economic_variance_pct,
                    matched_dimensions=pair.matched_dimensions,
                    unmatched_dimensions=pair.unmatched_dimensions,
                    reason=pair.reason,
                )
            )
        finding_summary = compute_finding_score(finding_pairs)
        finding_status = (
            ValidationDimensionStatus.SCORED.value
            if expected_findings
            else ValidationDimensionStatus.NOT_AVAILABLE.value
        )
        validation_score = ValidationScore(
            organization_id=organization_id,
            validation_run_id=validation_run.id,
            true_positive_count=finding_summary.true_positive_count,
            false_positive_count=finding_summary.false_positive_count,
            false_negative_count=finding_summary.false_negative_count,
            precision=finding_summary.precision,
            recall=finding_summary.recall,
            f1=finding_summary.f1,
            severity_accuracy=finding_summary.severity_accuracy,
            entity_accuracy=finding_summary.entity_accuracy,
            evidence_accuracy=finding_summary.evidence_accuracy,
            economic_variance_avg_pct=finding_summary.economic_variance_avg_pct,
            critical_leakage_recall=finding_summary.critical_leakage_recall,
        )
        db.add(validation_score)
        dimension_results.append(
            ValidationDimensionResult(
                organization_id=organization_id,
                validation_run_id=validation_run.id,
                dimension_code=ValidationDimensionCode.FINDING_DETECTION.value,
                status=finding_status,
                summary=(
                    f"{finding_summary.true_positive_count} matched, "
                    f"{finding_summary.false_positive_count} unexpected, "
                    f"{finding_summary.false_negative_count} missed."
                    if expected_findings
                    else "No expected findings were uploaded for this ground-truth version."
                ),
                metrics={
                    "true_positive_count": finding_summary.true_positive_count,
                    "false_positive_count": finding_summary.false_positive_count,
                    "false_negative_count": finding_summary.false_negative_count,
                    "precision": finding_summary.precision,
                    "recall": finding_summary.recall,
                    "f1": finding_summary.f1,
                    "severity_accuracy": finding_summary.severity_accuracy,
                    "entity_accuracy": finding_summary.entity_accuracy,
                    "evidence_accuracy": finding_summary.evidence_accuracy,
                    "economic_variance_avg_pct": finding_summary.economic_variance_avg_pct,
                    "critical_leakage_recall": finding_summary.critical_leakage_recall,
                },
            )
        )

        # B. Leakage / value accuracy.
        leakage_pairs = match_leakage(leakage_truth, actual_findings)
        for leakage_pair in leakage_pairs:
            db.add(
                ValidationFindingMatch(
                    organization_id=organization_id,
                    validation_run_id=validation_run.id,
                    dimension_code=ValidationDimensionCode.LEAKAGE_VALUE.value,
                    match_type=leakage_pair.match_type,
                    expected_leakage_truth_id=(
                        leakage_pair.expected.id if leakage_pair.expected else None
                    ),
                    actual_finding_id=(
                        leakage_pair.actual.finding.id if leakage_pair.actual else None
                    ),
                    economic_variance_pct=leakage_pair.economic_variance_pct,
                    reason=leakage_pair.reason,
                )
            )
        leakage_summary = compute_leakage_score(leakage_pairs)
        dimension_results.append(
            ValidationDimensionResult(
                organization_id=organization_id,
                validation_run_id=validation_run.id,
                dimension_code=ValidationDimensionCode.LEAKAGE_VALUE.value,
                status=leakage_summary.status,
                summary=leakage_summary.summary,
                metrics={
                    "true_positive_count": leakage_summary.true_positive_count,
                    "false_positive_count": leakage_summary.false_positive_count,
                    "false_negative_count": leakage_summary.false_negative_count,
                    "precision": leakage_summary.precision,
                    "recall": leakage_summary.recall,
                    "f1": leakage_summary.f1,
                    "total_true_leakage_value_by_currency": (
                        leakage_summary.total_true_leakage_value_by_currency
                    ),
                    "total_recoverable_value_by_currency": (
                        leakage_summary.total_recoverable_value_by_currency
                    ),
                    "value_weighted_recall": leakage_summary.value_weighted_recall,
                    "economic_variance_avg_pct": leakage_summary.economic_variance_avg_pct,
                },
            )
        )

        # C. Causal reasoning.
        causal_summary = score_causal(len(causal_truth))
        dimension_results.append(
            ValidationDimensionResult(
                organization_id=organization_id,
                validation_run_id=validation_run.id,
                dimension_code=ValidationDimensionCode.CAUSAL.value,
                status=causal_summary.status,
                summary=causal_summary.summary,
                metrics={"expected_count": causal_summary.expected_count},
            )
        )

        # D. Data quality.
        dq_summary = score_data_quality(dq_truth, actual_findings)
        dimension_results.append(
            ValidationDimensionResult(
                organization_id=organization_id,
                validation_run_id=validation_run.id,
                dimension_code=ValidationDimensionCode.DATA_QUALITY.value,
                status=dq_summary.status,
                summary=dq_summary.summary,
                metrics={
                    "true_positive_count": dq_summary.true_positive_count,
                    "false_positive_count": dq_summary.false_positive_count,
                    "false_negative_count": dq_summary.false_negative_count,
                    "precision": dq_summary.precision,
                    "recall": dq_summary.recall,
                    "f1": dq_summary.f1,
                },
            )
        )

        for dimension_result in dimension_results:
            db.add(dimension_result)

        validation_run.status = SimulationValidationRunStatus.COMPLETED.value
        validation_run.completed_at = datetime.now(UTC)
        db.add(validation_run)
        db.commit()
        db.refresh(validation_run)
        for dimension_result in dimension_results:
            db.refresh(dimension_result)

        matches = list(
            db.scalars(
                select(ValidationFindingMatch).where(
                    ValidationFindingMatch.validation_run_id == validation_run.id
                )
            ).all()
        )
        return validation_run, validation_score, dimension_results, matches

    def get_results(
        self, db: Session, organization_id: UUID, simulation_id: UUID
    ) -> list[
        tuple[
            SimulationValidationRun,
            ValidationScore | None,
            list[ValidationDimensionResult],
            list[ValidationFindingMatch],
        ]
    ]:
        self.get_simulation(db, organization_id, simulation_id)
        runs = list(
            db.scalars(
                select(SimulationValidationRun)
                .where(
                    SimulationValidationRun.organization_id == organization_id,
                    SimulationValidationRun.simulation_id == simulation_id,
                )
                .order_by(SimulationValidationRun.started_at.asc())
            ).all()
        )
        results = []
        for run in runs:
            score_row = db.scalar(
                select(ValidationScore).where(ValidationScore.validation_run_id == run.id)
            )
            dimensions = list(
                db.scalars(
                    select(ValidationDimensionResult).where(
                        ValidationDimensionResult.validation_run_id == run.id
                    )
                ).all()
            )
            matches = list(
                db.scalars(
                    select(ValidationFindingMatch).where(
                        ValidationFindingMatch.validation_run_id == run.id
                    )
                ).all()
            )
            results.append((run, score_row, dimensions, matches))
        return results


validation_service = ValidationService()
