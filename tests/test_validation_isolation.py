"""P3.xxD.1B, Section 6: the release-blocking ground-truth isolation
invariant. Ground truth existing for a simulation must have zero effect
on production AnalysisCase orchestration output -- not "probably no
effect," not "no effect by convention," but empirically identical output,
proven by literally re-running the same case before and after ground
truth is uploaded and diffing everything production actually produced."""

from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.ground_truth_validation.service import validation_service
from app.models.analysis_case import AnalysisCaseRunStatus
from app.models.entities import Organization
from app.schemas.contracts import OrganizationCreate
from app.services.analysis_case_command_service import analysis_case_command_service
from app.services.analysis_case_orchestration_service import analysis_case_orchestration_service
from app.services.analysis_case_service import AnalysisCaseService, UploadedFile
from app.services.organization_service import OrganizationService
from app.storage.local_storage import LocalFileStorage

MAINT_CSV = (
    b"asset_id,failure_code,downtime_hours,repair_cost,event_date\n"
    b"V1,brake,4,10000,2026-08-01T08:00:00\n"
    b"V1,brake,5,11000,2026-08-05T08:00:00\n"
    b"V1,brake,6,12000,2026-08-10T08:00:00\n"
)

GROUND_TRUTH_PAYLOAD = {
    "expected_findings": [
        {
            "expected_finding_code": "EXP-001",
            "domain": "maintenance",
            "severity": "high",
            "entities": [{"entity_type": "asset", "canonical_key": "V1"}],
            "evidence_refs": ["maintenance_events.csv"],
            "expected_economic_impact": 33000,
            "currency": "USD",
            "description": "Repeated brake failures on V1",
        }
    ],
    "expected_clean_areas": ["revenue"],
    "tolerance": {"economic_variance_pct": 15},
}


def _organization(db: Session, slug: str) -> Organization:
    return OrganizationService().create(
        db,
        OrganizationCreate(
            name=slug.title(), slug=slug, country_code="US", default_currency="USD", timezone="UTC"
        ),
    )


def _snapshot(db: Session, org_id: UUID, case_id: UUID, run_id: UUID) -> dict[str, object]:
    """Everything production actually produced for one run, excluding
    fields that are *expected* to differ between two runs of the same
    input (run id, run_number, timestamps)."""
    findings = analysis_case_command_service.priorities(db, org_id, case_id, run_id=run_id)
    from sqlalchemy import select

    from app.models.analysis_case import AnalysisCaseDataset

    datasets = list(
        db.scalars(
            select(AnalysisCaseDataset).where(
                AnalysisCaseDataset.organization_id == org_id,
                AnalysisCaseDataset.analysis_case_id == case_id,
            )
        ).all()
    )
    return {
        "findings": sorted(
            [
                (
                    f.finding.rule_id,
                    f.finding.severity,
                    f.finding.confidence_level,
                    f.finding.affected_record_count,
                    tuple(sorted(str(e) for e in (f.finding.entities_json or []))),
                    tuple(sorted(f.impacted_domains)),
                )
                for f in findings
            ]
        ),
        "datasets": sorted(
            (d.source_label, d.detected_domain, d.detection_status, d.mapping_status)
            for d in datasets
        ),
    }


def test_ground_truth_never_changes_production_orchestration_output(
    db: Session, tmp_path: Path
) -> None:
    service = AnalysisCaseService(storage=LocalFileStorage(str(tmp_path)))
    org = _organization(db, "isolation-invariant")
    actor = uuid4()

    case = service.create(db, org.id, "Isolation Invariant Case", "single", actor)
    service.register_artifacts(
        db, org.id, case.id, [UploadedFile("maintenance_events.csv", MAINT_CSV)], actor
    )

    # --- A/B/C: run with NO ground truth / simulation in existence at all ---
    run_before = analysis_case_orchestration_service.start_run(db, org.id, case.id, actor)
    analysis_case_orchestration_service.execute(
        db, service.storage, org.id, case.id, run_before.id, actor
    )
    db.refresh(run_before)
    assert run_before.status == AnalysisCaseRunStatus.COMPLETED.value
    snapshot_before = _snapshot(db, org.id, case.id, run_before.id)
    assert snapshot_before["findings"], "fixture must produce at least one finding to be meaningful"

    # --- D: create a simulation + ground truth for this exact case ---
    simulation = validation_service.create_simulation(
        db, org.id, "SIM-OFS-FIELDMAINT-001", "Isolation Invariant Simulation", case.id, actor
    )
    ground_truth = validation_service.upload_ground_truth(
        db, org.id, simulation.id, GROUND_TRUTH_PAYLOAD, actor
    )
    assert ground_truth.version == 1

    # --- E/F: re-run the identical AnalysisCase input ---
    run_after = analysis_case_orchestration_service.start_run(db, org.id, case.id, actor)
    analysis_case_orchestration_service.execute(
        db, service.storage, org.id, case.id, run_after.id, actor
    )
    db.refresh(run_after)
    assert run_after.status == AnalysisCaseRunStatus.COMPLETED.value
    snapshot_after = _snapshot(db, org.id, case.id, run_after.id)

    # --- ASSERT: production output is byte-for-byte identical ---
    assert snapshot_after["findings"] == snapshot_before["findings"]
    assert snapshot_after["datasets"] == snapshot_before["datasets"]
    assert run_after.status == run_before.status

    # Ground truth existing changed nothing about how the case runs -- run
    # numbering incrementing is the ONLY expected difference, proving these
    # genuinely are two independent executions, not a no-op.
    assert run_after.run_number == run_before.run_number + 1


def test_validating_a_run_does_not_mutate_the_run_it_validates(db: Session, tmp_path: Path) -> None:
    """Validation reads a terminal run's results; it must never write back
    to AnalysisCaseRun/Finding/AnalysisCase -- proven by comparing the run
    row before and after validate_run()."""
    service = AnalysisCaseService(storage=LocalFileStorage(str(tmp_path)))
    org = _organization(db, "isolation-no-mutation")
    actor = uuid4()

    case = service.create(db, org.id, "No Mutation Case", "single", actor)
    service.register_artifacts(
        db, org.id, case.id, [UploadedFile("maintenance_events.csv", MAINT_CSV)], actor
    )
    run = analysis_case_orchestration_service.start_run(db, org.id, case.id, actor)
    analysis_case_orchestration_service.execute(db, service.storage, org.id, case.id, run.id, actor)
    db.refresh(run)

    before = (run.status, run.completed_at, run.error_summary, run.run_number)

    simulation = validation_service.create_simulation(
        db, org.id, "SIM-OFS-FIELDMAINT-002", "No Mutation Simulation", case.id, actor
    )
    validation_service.upload_ground_truth(db, org.id, simulation.id, GROUND_TRUTH_PAYLOAD, actor)
    validation_service.validate_run(db, org.id, simulation.id, run.id, actor)

    db.refresh(run)
    after = (run.status, run.completed_at, run.error_summary, run.run_number)
    assert after == before


def test_validate_run_rejects_a_non_terminal_run(db: Session, tmp_path: Path) -> None:
    from app.ground_truth_validation.service import ValidationServiceError

    service = AnalysisCaseService(storage=LocalFileStorage(str(tmp_path)))
    org = _organization(db, "isolation-non-terminal")
    actor = uuid4()
    case = service.create(db, org.id, "Non Terminal Case", "single", actor)
    service.register_artifacts(
        db, org.id, case.id, [UploadedFile("maintenance_events.csv", MAINT_CSV)], actor
    )
    run = analysis_case_orchestration_service.start_run(db, org.id, case.id, actor)
    # deliberately never call execute() -- run stays "created"

    simulation = validation_service.create_simulation(
        db, org.id, "SIM-OFS-FIELDMAINT-003", "Non Terminal Simulation", case.id, actor
    )
    validation_service.upload_ground_truth(db, org.id, simulation.id, GROUND_TRUTH_PAYLOAD, actor)

    try:
        validation_service.validate_run(db, org.id, simulation.id, run.id, actor)
        raise AssertionError("expected ValidationServiceError for a non-terminal run")
    except ValidationServiceError as exc:
        assert exc.code == "run_not_terminal"
