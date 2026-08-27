"""Single-domain (MAINT-001) orchestration proof against the shared SQLite
test fixture. The full 3-domain SOTRA scenario (maintenance+operations+
revenue, all 3 findings including both cross-domain rules, and re-run
history preservation) was additionally verified live against a real
disposable PostgreSQL database -- see the certification report -- since
some governed Trust/finding-publication paths are most representatively
exercised there; this test proves the same orchestration mechanics
(status transitions, dataset tracking, governed publication, run
attribution) on the standard in-repo SQLite fixture."""

from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.analysis_case import AnalysisCaseRunStatus, AnalysisCaseStatus
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


def _organization(db: Session, slug: str) -> Organization:
    return OrganizationService().create(
        db,
        OrganizationCreate(
            name=slug.title(), slug=slug, country_code="US", default_currency="USD", timezone="UTC"
        ),
    )


def test_single_dataset_case_publishes_maint_001_finding(db: Session, tmp_path: Path) -> None:
    service = AnalysisCaseService(storage=LocalFileStorage(str(tmp_path)))
    org = _organization(db, "orch-single-maint")
    actor = uuid4()

    case = service.create(db, org.id, "Single Maintenance Case", "single", actor)
    assert case.status == AnalysisCaseStatus.CREATED.value

    service.register_artifacts(
        db, org.id, case.id, [UploadedFile("maintenance_events.csv", MAINT_CSV)], actor
    )
    datasets = service.list_datasets(db, org.id, case.id)
    assert len(datasets) == 1
    assert datasets[0].detected_domain == "maintenance"
    assert datasets[0].detection_status == "confirmed"
    assert datasets[0].row_count == 3

    run = analysis_case_orchestration_service.start_run(db, org.id, case.id, actor)
    assert run.run_number == 1
    assert run.status == AnalysisCaseRunStatus.CREATED.value

    analysis_case_orchestration_service.execute(db, service.storage, org.id, case.id, run.id, actor)
    db.refresh(run)
    db.refresh(case)
    assert run.status == AnalysisCaseRunStatus.COMPLETED.value
    assert case.status == AnalysisCaseStatus.COMPLETED.value
    assert run.completed_at is not None

    findings = analysis_case_command_service.priorities(db, org.id, case.id, run_id=run.id)
    assert len(findings) == 1
    finding = findings[0].finding
    assert finding.rule_id == "MAINT-001-REPEATED-FAILURE"
    assert finding.affected_record_count == 3
    assert finding.economic_status == "governed_pending"
    assert finding.exposure_value is None  # never a fabricated economic value


def test_duplicate_run_is_rejected_while_one_is_in_progress(db: Session, tmp_path: Path) -> None:
    from app.models.analysis_case import AnalysisCaseRunStatus as Status

    service = AnalysisCaseService(storage=LocalFileStorage(str(tmp_path)))
    org = _organization(db, "orch-duplicate-run")
    actor = uuid4()
    case = service.create(db, org.id, "Dup Run Case", "single", actor)
    service.register_artifacts(
        db, org.id, case.id, [UploadedFile("maintenance_events.csv", MAINT_CSV)], actor
    )
    run = analysis_case_orchestration_service.start_run(db, org.id, case.id, actor)
    run.status = Status.RUNNING.value
    db.add(run)
    db.commit()

    import pytest

    from app.services.analysis_case_orchestration_service import AnalysisCaseOrchestrationError

    with pytest.raises(AnalysisCaseOrchestrationError) as excinfo:
        analysis_case_orchestration_service.start_run(db, org.id, case.id, actor)
    assert excinfo.value.code == "run_already_in_progress"


def test_unsupported_artifact_is_preserved_not_dropped(db: Session, tmp_path: Path) -> None:
    service = AnalysisCaseService(storage=LocalFileStorage(str(tmp_path)))
    org = _organization(db, "orch-unsupported-artifact")
    actor = uuid4()
    case = service.create(db, org.id, "Mixed Artifact Case", "orchestrated", actor)

    artifacts = service.register_artifacts(
        db,
        org.id,
        case.id,
        [
            UploadedFile("maintenance_events.csv", MAINT_CSV),
            UploadedFile("scan.xyz", b"unrecognized binary content"),
        ],
        actor,
    )
    assert len(artifacts) == 2
    statuses = {a.original_filename: a.parser_status for a in artifacts}
    assert statuses["maintenance_events.csv"] == "parsed"
    assert statuses["scan.xyz"] == "unsupported"
    # the case still has exactly one usable dataset -- the unsupported
    # artifact never blocked or was silently discarded, it is preserved
    # with its own metadata and status.
    assert len(service.list_datasets(db, org.id, case.id)) == 1
