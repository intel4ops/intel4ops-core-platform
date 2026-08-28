from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.ground_truth_validation.matcher import match_findings
from app.ground_truth_validation.matcher import score as compute_score
from app.ground_truth_validation.normalizer import GroundTruthFormatError, normalize_ground_truth
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
    ValidationExpectedFinding,
    ValidationFindingMatch,
    ValidationGroundTruth,
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
        simulation = validation_ground_truth_repository.get_simulation(
            db, organization_id, simulation_id
        )
        if simulation is None:
            raise ValidationServiceError(
                "Simulation not found", code="simulation_not_found", status=404
            )
        try:
            normalized = normalize_ground_truth(payload)
        except GroundTruthFormatError as exc:
            raise ValidationServiceError(str(exc), code="ground_truth_format_error") from exc

        previous = validation_ground_truth_repository.latest_ground_truth(
            db, organization_id, simulation_id
        )
        version = (previous.version + 1) if previous is not None else 1

        raw_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
        checksum = hashlib.sha256(raw_bytes).hexdigest()
        write_result = write_ground_truth(
            self.storage, organization_id, simulation_id, version, raw_bytes
        )

        ground_truth = ValidationGroundTruth(
            organization_id=organization_id,
            simulation_id=simulation_id,
            version=version,
            storage_reference=write_result.reference,
            checksum=checksum,
            expected_clean_areas=normalized.expected_clean_areas,
            tolerance=normalized.tolerance,
            uploaded_by_user_id=actor_user_id,
        )
        db.add(ground_truth)
        db.flush()

        for expected in normalized.expected_findings:
            db.add(
                ValidationExpectedFinding(
                    organization_id=organization_id,
                    ground_truth_id=ground_truth.id,
                    expected_finding_code=expected.expected_finding_code,
                    domain=expected.domain,
                    severity=expected.severity,
                    entities=expected.entities,
                    evidence_refs=expected.evidence_refs,
                    expected_economic_impact=expected.expected_economic_impact,
                    currency=expected.currency,
                    description=expected.description,
                )
            )
        db.commit()
        db.refresh(ground_truth)
        return ground_truth

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
    ) -> tuple[SimulationValidationRun, ValidationScore, list[ValidationFindingMatch]]:
        # Local imports: analysis_case_command_service/models are the
        # PRODUCTION read path this module deliberately depends on (the one
        # allowed direction -- Validation reads Operational, never the
        # reverse). Kept local, not at module top, purely so
        # tests/test_validation_import_boundary.py's AST scan (which only
        # inspects the production-side files) has nothing to do with this
        # choice; it is a style choice, not a boundary mechanism -- the
        # actual enforcement is that production modules never import
        # anything from app.ground_truth_validation, checked by that same
        # test in the other direction.
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

        pairs = match_findings(
            expected_findings, actual_findings, dict(source_labels_by_finding_id)
        )
        for pair in pairs:
            db.add(
                ValidationFindingMatch(
                    organization_id=organization_id,
                    validation_run_id=validation_run.id,
                    match_type=pair.match_type,
                    expected_finding_id=(pair.expected.id if pair.expected else None),
                    actual_finding_id=(pair.actual.finding.id if pair.actual else None),
                    severity_match=pair.severity_match,
                    entity_match=pair.entity_match,
                    evidence_match=pair.evidence_match,
                    economic_variance_pct=pair.economic_variance_pct,
                )
            )

        summary = compute_score(pairs)
        validation_score = ValidationScore(
            organization_id=organization_id,
            validation_run_id=validation_run.id,
            true_positive_count=summary.true_positive_count,
            false_positive_count=summary.false_positive_count,
            false_negative_count=summary.false_negative_count,
            precision=summary.precision,
            recall=summary.recall,
            f1=summary.f1,
            severity_accuracy=summary.severity_accuracy,
            entity_accuracy=summary.entity_accuracy,
            evidence_accuracy=summary.evidence_accuracy,
            economic_variance_avg_pct=summary.economic_variance_avg_pct,
            critical_leakage_recall=summary.critical_leakage_recall,
        )
        db.add(validation_score)

        validation_run.status = SimulationValidationRunStatus.COMPLETED.value
        validation_run.completed_at = datetime.now(UTC)
        db.add(validation_run)
        db.commit()
        db.refresh(validation_run)
        db.refresh(validation_score)

        matches = list(
            db.scalars(
                select(ValidationFindingMatch).where(
                    ValidationFindingMatch.validation_run_id == validation_run.id
                )
            ).all()
        )
        return validation_run, validation_score, matches

    def get_results(
        self, db: Session, organization_id: UUID, simulation_id: UUID
    ) -> list[tuple[SimulationValidationRun, ValidationScore | None, list[ValidationFindingMatch]]]:
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
            matches = list(
                db.scalars(
                    select(ValidationFindingMatch).where(
                        ValidationFindingMatch.validation_run_id == run.id
                    )
                ).all()
            )
            results.append((run, score_row, matches))
        return results


validation_service = ValidationService()
