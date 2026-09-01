"""P3.xxV.1: the minimal Validation Program wave coordinator --
run_wave() triggers a production run for each registered simulation,
waits for it (execute() is synchronous), validates it, and is resumable
(a simulation already validated is skipped on a repeat call, never
re-scored)."""

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from app.ground_truth_validation.service import validation_service
from app.models.entities import Organization
from app.schemas.contracts import OrganizationCreate
from app.services.analysis_case_service import AnalysisCaseService, UploadedFile
from app.services.organization_service import OrganizationService
from app.storage.local_storage import LocalFileStorage
from app.validation_program.wave_coordinator import wave_coordinator

MAINT_CSV = (
    b"asset_id,failure_code,downtime_hours,repair_cost,event_date\n"
    b"V1,brake,4,10000,2026-08-01T08:00:00\n"
)


def _organization(db: Session, slug: str) -> Organization:
    return OrganizationService().create(
        db,
        OrganizationCreate(
            name=slug.title(), slug=slug, country_code="US", default_currency="USD", timezone="UTC"
        ),
    )


def _registered_simulation(
    db: Session, tmp_path: Path, org: Organization, simulation_code: str
) -> tuple[UUID, AnalysisCaseService]:
    """A case exists and a simulation is registered with ground truth, but
    NO run has happened yet -- run_wave is responsible for triggering it."""
    service = AnalysisCaseService(storage=LocalFileStorage(str(tmp_path / simulation_code)))
    actor = uuid4()
    case = service.create(db, org.id, "Wave Case", "single", actor)
    service.register_artifacts(
        db, org.id, case.id, [UploadedFile("maintenance_events.csv", MAINT_CSV)], actor
    )
    simulation = validation_service.create_simulation(
        db, org.id, simulation_code, simulation_code, case.id, actor
    )
    validation_service.upload_ground_truth(
        db,
        org.id,
        simulation.id,
        {
            "expected_findings": [
                {"expected_finding_code": "EXP-001", "domain": "maintenance", "severity": "high"}
            ]
        },
        actor,
    )
    return case.id, service


def test_run_wave_scores_a_registered_simulation(db: Session, tmp_path: Path) -> None:
    org = _organization(db, "wave-basic")
    case_id, service = _registered_simulation(db, tmp_path, org, "SIM-WAVE-001")

    summary = wave_coordinator.run_wave(
        db, service.storage, org.id, {"SIM-WAVE-001": case_id}, uuid4()
    )
    assert summary.members == 1
    assert summary.scored == 1
    assert summary.results[0].outcome == "scored"
    assert summary.results[0].analysis_case_run_id is not None

    simulation = validation_service.get_simulation_by_code(db, org.id, "SIM-WAVE-001")
    results_for_sim = validation_service.get_results(db, org.id, simulation.id)
    assert len(results_for_sim) == 1


def test_run_wave_is_resumable_and_never_rescoresa_completed_member(
    db: Session, tmp_path: Path
) -> None:
    org = _organization(db, "wave-resume")
    case_id, service = _registered_simulation(db, tmp_path, org, "SIM-WAVE-002")

    first = wave_coordinator.run_wave(
        db, service.storage, org.id, {"SIM-WAVE-002": case_id}, uuid4()
    )
    assert first.scored == 1

    second = wave_coordinator.run_wave(
        db, service.storage, org.id, {"SIM-WAVE-002": case_id}, uuid4()
    )
    assert second.scored == 0
    assert second.already_scored == 1
    assert second.results[0].outcome == "already_scored"

    simulation = validation_service.get_simulation_by_code(db, org.id, "SIM-WAVE-002")
    assert len(validation_service.get_results(db, org.id, simulation.id)) == 1


def test_run_wave_reports_not_registered_without_failing_the_wave(
    db: Session, tmp_path: Path
) -> None:
    org = _organization(db, "wave-not-registered")
    service = AnalysisCaseService(storage=LocalFileStorage(str(tmp_path / "unregistered")))
    actor = uuid4()
    case = service.create(db, org.id, "Unregistered Case", "single", actor)
    service.register_artifacts(
        db, org.id, case.id, [UploadedFile("maintenance_events.csv", MAINT_CSV)], actor
    )

    summary = wave_coordinator.run_wave(
        db, service.storage, org.id, {"SIM-NEVER-REGISTERED": case.id}, uuid4()
    )
    assert summary.members == 1
    assert summary.not_registered == 1
    assert summary.results[0].outcome == "not_registered"


def test_run_wave_processes_multiple_members_sequentially(db: Session, tmp_path: Path) -> None:
    org = _organization(db, "wave-multi")
    # a shared storage backend across both members -- each real member of a
    # real wave shares one storage root; the earlier single-member tests
    # used a per-call root purely for isolation between unrelated tests.
    shared_storage = LocalFileStorage(str(tmp_path / "shared"))
    actor = uuid4()

    def _register(simulation_code: str) -> UUID:
        service = AnalysisCaseService(storage=shared_storage)
        case = service.create(db, org.id, "Wave Case", "single", actor)
        service.register_artifacts(
            db, org.id, case.id, [UploadedFile("maintenance_events.csv", MAINT_CSV)], actor
        )
        simulation = validation_service.create_simulation(
            db, org.id, simulation_code, simulation_code, case.id, actor
        )
        validation_service.upload_ground_truth(
            db,
            org.id,
            simulation.id,
            {
                "expected_findings": [
                    {
                        "expected_finding_code": "EXP-001",
                        "domain": "maintenance",
                        "severity": "high",
                    }
                ]
            },
            actor,
        )
        return case.id

    case_a = _register("SIM-WAVE-A")
    case_b = _register("SIM-WAVE-B")

    summary = wave_coordinator.run_wave(
        db, shared_storage, org.id, {"SIM-WAVE-A": case_a, "SIM-WAVE-B": case_b}, uuid4()
    )
    assert summary.members == 2
    assert summary.scored == 2


def test_run_wave_run_failure_is_recorded_not_fatal(
    db: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    org = _organization(db, "wave-run-failure")
    case_id, service = _registered_simulation(db, tmp_path, org, "SIM-WAVE-FAIL")

    import app.validation_program.wave_coordinator as coordinator_module

    def _boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated production execution failure")

    monkeypatch.setattr(coordinator_module.analysis_case_orchestration_service, "execute", _boom)

    summary = wave_coordinator.run_wave(
        db, service.storage, org.id, {"SIM-WAVE-FAIL": case_id}, uuid4()
    )
    assert summary.failed == 1
    assert summary.results[0].outcome == "run_failed"
