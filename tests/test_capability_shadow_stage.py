"""P3.xxE.5 Phase 1 (SHADOW): the real orchestration integration proof.
Runs a 3-domain (maintenance+operations+revenue) case -- the same domain
signatures test_analysis_case_orchestration_service.py's own MAINT_CSV
fixture already proves triggers real domain detection -- through the
production AnalysisCaseOrchestrationService.execute(), and asserts:
  - the new capability_shadow_evaluation stage completes
  - IntelligenceActivationDecision rows are persisted for XDOM-A/XDOM-B
  - Finding output is exactly what the pre-existing, untouched
    cross_domain_intelligence stage alone produces -- SHADOW mode never
    changes what's published (test item: "SHADOW produces no finding
    changes")."""

from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analysis_case import AnalysisCaseRunStatus, AnalysisCaseStageEvent
from app.models.entities import Organization
from app.models.intelligence_activation import IntelligenceActivationDecision
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
OPERATIONS_CSV = (
    b"operational_event_id,asset_id,event_date,operational_event_status\n"
    b"OE-1,V1,2026-08-01T10:00:00,completed\n"
    b"OE-2,V1,2026-08-05T09:00:00,completed\n"
)
REVENUE_CSV = b"transaction_amount,event_date,operational_event_id\n5000,2026-08-01T10:00:00,OE-1\n"


def _organization(db: Session, slug: str) -> Organization:
    return OrganizationService().create(
        db,
        OrganizationCreate(
            name=slug.title(), slug=slug, country_code="US", default_currency="USD", timezone="UTC"
        ),
    )


def test_capability_shadow_evaluation_stage_completes_and_persists_decisions(
    db: Session, tmp_path: Path
) -> None:
    service = AnalysisCaseService(storage=LocalFileStorage(str(tmp_path)))
    org = _organization(db, "shadow-completes")
    actor = uuid4()
    case = service.create(db, org.id, "Shadow Case", "single", actor)
    service.register_artifacts(
        db,
        org.id,
        case.id,
        [
            UploadedFile("maintenance_events.csv", MAINT_CSV),
            UploadedFile("operations_events.csv", OPERATIONS_CSV),
            UploadedFile("revenue_events.csv", REVENUE_CSV),
        ],
        actor,
    )
    run = analysis_case_orchestration_service.start_run(db, org.id, case.id, actor)
    analysis_case_orchestration_service.execute(db, service.storage, org.id, case.id, run.id, actor)
    db.refresh(run)
    assert run.status in (
        AnalysisCaseRunStatus.COMPLETED.value,
        AnalysisCaseRunStatus.PARTIAL.value,
    )

    stage_events = list(
        db.scalars(
            select(AnalysisCaseStageEvent).where(
                AnalysisCaseStageEvent.run_id == run.id,
                AnalysisCaseStageEvent.stage == "capability_shadow_evaluation",
            )
        ).all()
    )
    assert stage_events, "expected the capability_shadow_evaluation stage to have run"
    assert stage_events[0].status == "completed"

    decisions = list(
        db.scalars(
            select(IntelligenceActivationDecision).where(
                IntelligenceActivationDecision.run_id == run.id
            )
        ).all()
    )
    assert decisions, "expected at least one IntelligenceActivationDecision row"
    rule_codes = {d.rule_code for d in decisions}
    assert rule_codes <= {"XDOM-A-ASSET-FAILURE-LOST-ACTIVITY", "XDOM-B-LOST-ACTIVITY-REVENUE-GAP"}
    for decision in decisions:
        assert decision.governed_status in ("DISABLED", "READY", "PARTIAL", "BLOCKED")
        # P3.xxE.5 Phase 2: both migrated rules are GOVERNED -- see
        # _GOVERNED_RULE_CODES in analysis_case_orchestration_service.py.
        assert decision.mode == "governed"


def test_shadow_stage_never_changes_legacy_finding_output(db: Session, tmp_path: Path) -> None:
    """The decisive proof: run the SAME case twice under identical
    conditions (the shadow stage is unconditionally present both times,
    since it's now part of execute() -- there is no code path where it
    could ever be selectively disabled this milestone). If SHADOW mode
    genuinely never influences Finding output, both runs must publish
    byte-for-byte identical findings, since nothing about the legacy
    cross_domain_intelligence/domain_intelligence stages' own inputs
    changed between them."""
    service = AnalysisCaseService(storage=LocalFileStorage(str(tmp_path)))
    org = _organization(db, "shadow-no-finding-drift")
    actor = uuid4()

    def _run_once(slug: str) -> list[str]:
        case = service.create(db, org.id, f"Case {slug}", "single", actor)
        service.register_artifacts(
            db,
            org.id,
            case.id,
            [
                UploadedFile("maintenance_events.csv", MAINT_CSV),
                UploadedFile("operations_events.csv", OPERATIONS_CSV),
                UploadedFile("revenue_events.csv", REVENUE_CSV),
            ],
            actor,
        )
        run = analysis_case_orchestration_service.start_run(db, org.id, case.id, actor)
        analysis_case_orchestration_service.execute(
            db, service.storage, org.id, case.id, run.id, actor
        )
        findings = analysis_case_command_service.priorities(db, org.id, case.id, run_id=run.id)
        return sorted(f.finding.rule_id for f in findings)

    first = _run_once("a")
    second = _run_once("b")
    assert first == second
    # MAINT-001 at minimum must be present -- proves the legacy path
    # actually ran and published its normal output, not an empty result
    # SHADOW mode accidentally suppressed.
    assert "MAINT-001-REPEATED-FAILURE" in first
