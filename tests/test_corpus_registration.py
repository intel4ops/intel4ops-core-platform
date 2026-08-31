"""P3.xxV.1A: idempotent folder-corpus registration
(ValidationService.register_corpus()) -- discovers packages from a folder,
validates them, and registers each READY one against the existing
single-simulation ValidationService primitives (create_simulation /
upload_ground_truth), never overwriting an existing registration with
different truth content."""

from pathlib import Path
from uuid import UUID, uuid4

from corpus_discovery_fixtures import valid_package
from sqlalchemy.orm import Session

from app.ground_truth_validation.service import validation_service
from app.models.entities import Organization
from app.schemas.contracts import OrganizationCreate
from app.services.analysis_case_orchestration_service import analysis_case_orchestration_service
from app.services.analysis_case_service import AnalysisCaseService, UploadedFile
from app.services.organization_service import OrganizationService
from app.storage.local_storage import LocalFileStorage

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


def _completed_run(db: Session, tmp_path: Path, org: Organization) -> tuple[UUID, UUID]:
    service = AnalysisCaseService(storage=LocalFileStorage(str(tmp_path / "storage")))
    actor = uuid4()
    case = service.create(db, org.id, "Case", "single", actor)
    service.register_artifacts(
        db, org.id, case.id, [UploadedFile("maintenance_events.csv", MAINT_CSV)], actor
    )
    run = analysis_case_orchestration_service.start_run(db, org.id, case.id, actor)
    analysis_case_orchestration_service.execute(db, service.storage, org.id, case.id, run.id, actor)
    return case.id, actor


def test_j_corpus_registration_is_idempotent(db: Session, tmp_path: Path) -> None:
    corpus_root = tmp_path / "corpus"
    valid_package(corpus_root, "TestFamily", "SIM-REG-001")
    org = _organization(db, "corpus-reg-idempotent")
    case_id, actor = _completed_run(db, tmp_path, org)

    first = validation_service.register_corpus(
        db, org.id, corpus_root, {"SIM-REG-001": case_id}, actor
    )
    assert first.discovered == 1
    assert first.newly_registered == 1
    assert first.already_registered == 0

    second = validation_service.register_corpus(
        db, org.id, corpus_root, {"SIM-REG-001": case_id}, actor
    )
    assert second.newly_registered == 0
    assert second.already_registered == 1
    assert second.conflicts == 0


def test_k_truth_registration_immutable_conflict_on_different_hash(
    db: Session, tmp_path: Path
) -> None:
    """A same-code package whose truth content actually differs (e.g. the
    corpus folder was regenerated with a different seed) must be reported
    as a conflict, never silently applied over the existing registration."""
    corpus_root = tmp_path / "corpus"
    valid_package(corpus_root, "TestFamily", "SIM-REG-002", leakage_value=100.0)
    org = _organization(db, "corpus-reg-conflict")
    case_id, actor = _completed_run(db, tmp_path, org)

    first = validation_service.register_corpus(
        db, org.id, corpus_root, {"SIM-REG-002": case_id}, actor
    )
    assert first.newly_registered == 1

    # regenerate the SAME simulation_id with genuinely different truth content
    valid_package(corpus_root, "TestFamily", "SIM-REG-002", leakage_value=999.0)
    second = validation_service.register_corpus(
        db, org.id, corpus_root, {"SIM-REG-002": case_id}, actor
    )
    assert second.conflicts == 1
    assert second.newly_registered == 0
    conflict = next(o for o in second.outcomes if o.outcome == "conflict")
    assert conflict.simulation_id == "SIM-REG-002"


def test_ready_package_without_case_id_is_awaiting_case(db: Session, tmp_path: Path) -> None:
    corpus_root = tmp_path / "corpus"
    valid_package(corpus_root, "TestFamily", "SIM-REG-003")
    org = _organization(db, "corpus-reg-awaiting")
    summary = validation_service.register_corpus(db, org.id, corpus_root, {}, uuid4())
    assert summary.discovered == 1
    assert summary.awaiting_case == 1
    assert summary.newly_registered == 0


def test_non_ready_packages_counted_and_not_registered(db: Session, tmp_path: Path) -> None:
    corpus_root = tmp_path / "corpus"
    broken_dir = corpus_root / "TestFamily" / "SIM-REG-BROKEN"
    (broken_dir / "customer-data").mkdir(parents=True)
    (broken_dir / "customer-data" / "events.csv").write_text("a,b\n1,2\n")
    org = _organization(db, "corpus-reg-nonready")
    summary = validation_service.register_corpus(db, org.id, corpus_root, {}, uuid4())
    assert summary.discovered == 1
    assert summary.missing_truth == 1
    assert summary.ready == 0
