"""P3.xxE.1 section 35-L / section 31: semantic interpretation is additive.
A full AnalysisCase run still produces its existing findings/mapping
output unchanged, AND now also produces semantic profile/role/decision
rows -- proving the new layer runs alongside, never in place of, existing
production analysis."""

from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analysis_case import AnalysisCaseRunStatus
from app.models.entities import Organization
from app.models.semantic import (
    SemanticDatasetProfile,
    SemanticInterpretationDecision,
    SemanticRoleInterpretation,
)
from app.schemas.contracts import OrganizationCreate
from app.services.analysis_case_command_service import analysis_case_command_service
from app.services.analysis_case_orchestration_service import analysis_case_orchestration_service
from app.services.analysis_case_semantic_service import analysis_case_semantic_service
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


def test_existing_analysis_case_findings_are_unchanged_by_the_semantic_layer(
    db: Session, tmp_path: Path
) -> None:
    """L: the exact same maintenance scenario proven in
    test_analysis_case_orchestration_service.py still produces the same
    MAINT-001 finding, unmodified by P3.xxE.1's presence."""
    service = AnalysisCaseService(storage=LocalFileStorage(str(tmp_path)))
    org = _organization(db, "semantic-existing-findings")
    actor = uuid4()
    case = service.create(db, org.id, "Single Maintenance Case", "single", actor)
    service.register_artifacts(
        db, org.id, case.id, [UploadedFile("maintenance_events.csv", MAINT_CSV)], actor
    )
    run = analysis_case_orchestration_service.start_run(db, org.id, case.id, actor)
    analysis_case_orchestration_service.execute(db, service.storage, org.id, case.id, run.id, actor)
    db.refresh(run)
    db.refresh(case)

    assert run.status == AnalysisCaseRunStatus.COMPLETED.value
    findings = analysis_case_command_service.priorities(db, org.id, case.id, run_id=run.id)
    assert len(findings) == 1
    assert findings[0].finding.rule_id == "MAINT-001-REPEATED-FAILURE"


def test_semantic_interpretation_results_are_persisted_alongside_the_run(
    db: Session, tmp_path: Path
) -> None:
    service = AnalysisCaseService(storage=LocalFileStorage(str(tmp_path)))
    org = _organization(db, "semantic-persisted")
    actor = uuid4()
    case = service.create(db, org.id, "Semantic Persistence Case", "single", actor)
    service.register_artifacts(
        db, org.id, case.id, [UploadedFile("maintenance_events.csv", MAINT_CSV)], actor
    )
    run = analysis_case_orchestration_service.start_run(db, org.id, case.id, actor)
    analysis_case_orchestration_service.execute(db, service.storage, org.id, case.id, run.id, actor)
    db.refresh(run)

    profiles = list(
        db.scalars(
            select(SemanticDatasetProfile).where(SemanticDatasetProfile.run_id == run.id)
        ).all()
    )
    roles = list(
        db.scalars(
            select(SemanticRoleInterpretation).where(SemanticRoleInterpretation.run_id == run.id)
        ).all()
    )
    decisions = list(
        db.scalars(
            select(SemanticInterpretationDecision).where(
                SemanticInterpretationDecision.run_id == run.id
            )
        ).all()
    )
    assert len(profiles) == 1
    assert profiles[0].row_count == 3
    assert profiles[0].column_count == 5
    assert len(roles) == 1
    assert len(decisions) == 5  # one per source column

    asset_id_decision = next(d for d in decisions if d.source_field == "asset_id")
    assert asset_id_decision.selected_concept == "asset_id"


def test_semantic_read_service_returns_the_same_data_navigator_would_see(
    db: Session, tmp_path: Path
) -> None:
    service = AnalysisCaseService(storage=LocalFileStorage(str(tmp_path)))
    org = _organization(db, "semantic-read-service")
    actor = uuid4()
    case = service.create(db, org.id, "Semantic Read Case", "single", actor)
    service.register_artifacts(
        db, org.id, case.id, [UploadedFile("maintenance_events.csv", MAINT_CSV)], actor
    )
    run = analysis_case_orchestration_service.start_run(db, org.id, case.id, actor)
    analysis_case_orchestration_service.execute(db, service.storage, org.id, case.id, run.id, actor)

    views = analysis_case_semantic_service.get_case_semantic_view(db, org.id, case.id, run.id)
    assert len(views) == 1
    view = views[0]
    assert view.source_label == "maintenance_events.csv"
    assert view.role is not None
    assert view.profile is not None
    assert len(view.field_decisions) == 5


def test_a_semantic_interpretation_failure_never_fails_the_run(
    db: Session, tmp_path: Path, monkeypatch: object
) -> None:
    """The additive layer is wrapped in a try/except in
    AnalysisCaseOrchestrationService._run_semantic_interpretation's caller
    -- proven directly by forcing interpret_dataset to raise and
    confirming the run still completes normally."""
    import app.services.analysis_case_orchestration_service as orchestration_module

    def _boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated semantic layer failure")

    original = orchestration_module.interpret_dataset
    orchestration_module.interpret_dataset = _boom  # type: ignore[assignment]
    try:
        service = AnalysisCaseService(storage=LocalFileStorage(str(tmp_path)))
        org = _organization(db, "semantic-failure-non-blocking")
        actor = uuid4()
        case = service.create(db, org.id, "Semantic Failure Case", "single", actor)
        service.register_artifacts(
            db, org.id, case.id, [UploadedFile("maintenance_events.csv", MAINT_CSV)], actor
        )
        run = analysis_case_orchestration_service.start_run(db, org.id, case.id, actor)
        analysis_case_orchestration_service.execute(
            db, service.storage, org.id, case.id, run.id, actor
        )
        db.refresh(run)
        assert run.status == AnalysisCaseRunStatus.COMPLETED.value
        findings = analysis_case_command_service.priorities(db, org.id, case.id, run_id=run.id)
        assert len(findings) == 1
    finally:
        orchestration_module.interpret_dataset = original
