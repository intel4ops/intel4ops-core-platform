"""P3.xxV.2C: XDOM-B (run_lost_activity_to_revenue_gap) must consume the
canonical operational state produced by the shared, generic
app/process/state_normalization.py vocabulary, never a raw source-system
status literal. Reuses the exact real-orchestrator harness pattern already
established in test_capability_governed_activation.py/test_capability_shadow_stage.py
so these are genuine end-to-end proofs (real case, real run, real published
finding), not mocked candidate-elimination checks.

Fixtures are deliberately generic (OE-1/OE-2/V1/etc, no simulation ID,
business family, or filename ever appears in a status value)."""

from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.models.entities import Organization
from app.schemas.contracts import OrganizationCreate
from app.services.analysis_case_command_service import analysis_case_command_service
from app.services.analysis_case_orchestration_service import analysis_case_orchestration_service
from app.services.analysis_case_service import AnalysisCaseService, UploadedFile
from app.services.organization_service import OrganizationService
from app.storage.local_storage import LocalFileStorage

_XDOM_B = "XDOM-B-LOST-ACTIVITY-REVENUE-GAP"

MAINT_CSV = (
    b"asset_id,failure_code,downtime_hours,repair_cost,event_date\n"
    b"V1,brake,4,10000,2026-08-01T08:00:00\n"
    b"V1,brake,5,11000,2026-08-05T08:00:00\n"
    b"V1,brake,6,12000,2026-08-10T08:00:00\n"
)
REVENUE_CSV = b"transaction_amount,event_date,operational_event_id\n5000,2026-08-01T10:00:00,OE-1\n"


def _operations_csv(status_value: str) -> bytes:
    return (
        b"operational_event_id,asset_id,event_date,operational_event_status\n"
        b"OE-1,V1,2026-08-01T10:00:00," + status_value.encode() + b"\n"
        b"OE-2,V1,2026-08-05T09:00:00," + status_value.encode() + b"\n"
    )


def _operations_csv_no_status_column() -> bytes:
    return (
        b"operational_event_id,asset_id,event_date\n"
        b"OE-1,V1,2026-08-01T10:00:00\n"
        b"OE-2,V1,2026-08-05T09:00:00\n"
    )


def _organization(db: Session, slug: str) -> Organization:
    return OrganizationService().create(
        db,
        OrganizationCreate(
            name=slug.title(), slug=slug, country_code="US", default_currency="USD", timezone="UTC"
        ),
    )


def _run_case(
    db: Session, tmp_path: Path, org_id: UUID, files: list[UploadedFile]
) -> tuple[UUID, UUID]:
    service = AnalysisCaseService(storage=LocalFileStorage(str(tmp_path)))
    actor = uuid4()
    case = service.create(db, org_id, "State Normalization Case", "single", actor)
    service.register_artifacts(db, org_id, case.id, files, actor)
    run = analysis_case_orchestration_service.start_run(db, org_id, case.id, actor)
    analysis_case_orchestration_service.execute(db, service.storage, org_id, case.id, run.id, actor)
    return case.id, run.id


def _xdom_b_finding_count(db: Session, org_id: UUID, case_id: UUID, run_id: UUID) -> int:
    priorities = analysis_case_command_service.priorities(db, org_id, case_id, run_id=run_id)
    return len([p for p in priorities if p.finding.rule_id == _XDOM_B])


def _run_with_status(db: Session, tmp_path: Path, slug: str, status_value: str) -> int:
    org = _organization(db, slug)
    case_id, run_id = _run_case(
        db,
        tmp_path,
        org.id,
        [
            UploadedFile("maintenance_events.csv", MAINT_CSV),
            UploadedFile("operations_events.csv", _operations_csv(status_value)),
            UploadedFile("revenue_events.csv", REVENUE_CSV),
        ],
    )
    return _xdom_b_finding_count(db, org.id, case_id, run_id)


def test_a_raw_completed_still_produces_a_finding(db: Session, tmp_path: Path) -> None:
    """A -- regression safety: the pre-existing "completed" behavior is
    unchanged by routing through canonical-state lookup."""
    assert _run_with_status(db, tmp_path, "state-a-completed", "completed") == 1


def test_b_raw_closed_now_produces_a_finding(db: Session, tmp_path: Path) -> None:
    """B -- the actual fix: CLOSED (FieldMaintenance's real vocabulary,
    Wave 1 Section I) now normalizes to a canonical state Rule B accepts,
    where it previously eliminated every candidate at Stage 0."""
    assert _run_with_status(db, tmp_path, "state-b-closed", "CLOSED") == 1


def test_c_case_and_whitespace_variants_normalize_the_same_way(db: Session, tmp_path: Path) -> None:
    """C -- normalization policy applies consistently regardless of source
    casing/whitespace, matching state_normalization.py's own policy."""
    assert _run_with_status(db, tmp_path, "state-c-mixed-case", "  Closed  ") == 1
    assert _run_with_status(db, tmp_path, "state-c-upper", "COMPLETED") == 1


def test_d_open_is_not_eligible(db: Session, tmp_path: Path) -> None:
    assert _run_with_status(db, tmp_path, "state-d-open", "open") == 0


def test_e_in_progress_is_not_eligible(db: Session, tmp_path: Path) -> None:
    assert _run_with_status(db, tmp_path, "state-e-in-progress", "in_progress") == 0


def test_f_cancelled_is_not_eligible(db: Session, tmp_path: Path) -> None:
    assert _run_with_status(db, tmp_path, "state-f-cancelled", "cancelled") == 0


def test_g_missing_status_column_does_not_fabricate_completion(db: Session, tmp_path: Path) -> None:
    """G -- Rental's real shape (dispatch.csv has no status column at all,
    Wave 1 Section I): must remain zero candidates, never inferred."""
    org = _organization(db, "state-g-missing-status")
    case_id, run_id = _run_case(
        db,
        tmp_path,
        org.id,
        [
            UploadedFile("maintenance_events.csv", MAINT_CSV),
            UploadedFile("operations_events.csv", _operations_csv_no_status_column()),
            UploadedFile("revenue_events.csv", REVENUE_CSV),
        ],
    )
    assert _xdom_b_finding_count(db, org.id, case_id, run_id) == 0


def test_h_unrecognized_status_value_stays_governed_uncertainty(
    db: Session, tmp_path: Path
) -> None:
    """H -- an arbitrary, unmatched status string never fabricates
    COMPLETED/CLOSED eligibility -- it is excluded, not guessed."""
    assert _run_with_status(db, tmp_path, "state-h-unrecognized", "frobnicated") == 0


def test_j_no_raw_status_literal_comparison_in_cross_domain_service() -> None:
    """J/K -- guardrail: the rule module itself must never compare a raw
    status value against a hardcoded literal (source-family-specific or
    simulation-specific) again -- canonical-state membership only. A plain
    source-text scan, deliberately simple and directly readable, rather
    than an AST walk, since the anti-pattern is a literal string
    comparison, not a structural shape."""
    from pathlib import Path as _Path

    source = _Path("app/services/cross_domain_intelligence_service.py").read_text(encoding="utf-8")
    assert '== "completed"' not in source
    assert "== 'completed'" not in source
    assert ".str.lower()" not in source
