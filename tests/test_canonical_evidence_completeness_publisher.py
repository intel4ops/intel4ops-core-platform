"""P3.xxV.2D end-to-end proof: governed_finding_publisher no longer falsely
rejects a finding candidate whose required canonical evidence is only
available via an ALIASED raw field (e.g. work_order_id -> operational_event_id)
-- the exact P3.xxV.2C NEXT-1 defect (app/engines/trust_engine.py's
RequiredFieldCompletenessRule checking raw dict keys against canonical
names). Real orchestrator harness, same pattern as
test_capability_governed_activation.py / test_cross_domain_intelligence_operational_state.py.

Deliberately uses work_order_id (never operational_event_id literally) as the
operations dataset's identifier column -- the prior test files' fixtures all
use operational_event_id literally, which never exercised this bug at all."""

from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Organization
from app.models.trust import AnalyticalLevel, AnalyticalReadinessDecision
from app.schemas.contracts import OrganizationCreate
from app.services.analysis_case_command_service import analysis_case_command_service
from app.services.analysis_case_orchestration_service import analysis_case_orchestration_service
from app.services.analysis_case_service import AnalysisCaseService, UploadedFile
from app.services.organization_service import OrganizationService
from app.storage.local_storage import LocalFileStorage

_XDOM_B = "XDOM-B-LOST-ACTIVITY-REVENUE-GAP"

# asset_id unique per row (V1..V10); a second, independent dataset
# (field_tickets.csv) references the SAME work-order identifiers via its own
# alias (ticket_id/work_order_id) -- exactly mirroring the real corpus shape
# (work_orders.csv + field_tickets.csv) that gives the semantic confidence
# engine the cross-dataset corroboration it needs to reach AUTO_ACCEPTED for
# an aliased identifier. A single-dataset, low-row-count fixture is not
# enough to exercise this realistically (confirmed empirically while writing
# this test) -- this shape is what the real corpus actually looks like.
_N = 10
MAINT_CSV = b"asset_id,failure_code,downtime_hours,repair_cost,event_date\n" + b"".join(
    f"V{i},brake,{4 + i},1000{i},2026-08-{(i % 28) + 1:02d}T08:00:00\n".encode()
    for i in range(1, _N + 1)
)
# work_order_id, NOT operational_event_id -- an alias, exercising the exact
# raw-vs-canonical mismatch NEXT-1 identified. status uses "CLOSED" (the
# P3.xxV.2C canonical-state fix) so both fixes' combined effect is visible.
OPERATIONS_CSV = b"work_order_id,asset_id,event_date,operational_event_status\n" + b"".join(
    f"WO-{i:04d},V{i},2026-08-{(i % 28) + 1:02d}T10:00:00,CLOSED\n".encode()
    for i in range(1, _N + 1)
)
FIELD_TICKETS_CSV = b"ticket_id,work_order_id,hours_reported,ticket_date\n" + b"".join(
    f"TK-{i:04d},WO-{i:04d},4.0,2026-08-{(i % 28) + 1:02d}\n".encode() for i in range(1, _N + 1)
)
# No revenue record for WO-0002..WO-0010 -- genuine unmatched candidates.
REVENUE_CSV = (
    b"transaction_amount,event_date,operational_event_id\n5000,2026-08-01T10:00:00,WO-0001\n"
)


def _organization(db: Session, slug: str) -> Organization:
    return OrganizationService().create(
        db,
        OrganizationCreate(
            name=slug.title(), slug=slug, country_code="US", default_currency="USD", timezone="UTC"
        ),
    )


def _run_case(db: Session, tmp_path: Path, org_id: UUID) -> tuple[UUID, UUID]:
    service = AnalysisCaseService(storage=LocalFileStorage(str(tmp_path)))
    actor = uuid4()
    case = service.create(db, org_id, "Canonical Evidence Completeness Case", "single", actor)
    service.register_artifacts(
        db,
        org_id,
        case.id,
        [
            UploadedFile("maintenance_events.csv", MAINT_CSV),
            UploadedFile("operations_events.csv", OPERATIONS_CSV),
            UploadedFile("revenue_events.csv", REVENUE_CSV),
            UploadedFile("field_tickets.csv", FIELD_TICKETS_CSV),
        ],
        actor,
    )
    run = analysis_case_orchestration_service.start_run(db, org_id, case.id, actor)
    analysis_case_orchestration_service.execute(db, service.storage, org_id, case.id, run.id, actor)
    return case.id, run.id


def test_j_aliased_canonical_evidence_no_longer_falsely_rejected(
    db: Session, tmp_path: Path
) -> None:
    org = _organization(db, "canonical-evidence-alias")
    case_id, run_id = _run_case(db, tmp_path, org.id)
    priorities = analysis_case_command_service.priorities(db, org.id, case_id, run_id=run_id)
    xdom_b_findings = [p for p in priorities if p.finding.rule_id == _XDOM_B]
    assert xdom_b_findings, (
        "expected a real XDOM-B finding once work_order_id's governed semantic "
        "evidence satisfies the operational_event_id requirement -- the exact "
        "NEXT-1 regression this test guards against"
    )


def test_original_early_trust_readiness_decision_is_preserved_unchanged(
    db: Session, tmp_path: Path
) -> None:
    """Section 16 safety: the ORIGINAL early-Trust ARITHMETIC readiness
    decision (raw dataset quality, computed before mapping/semantic
    interpretation) must still report BLOCKED/required_field_completeness
    after governed publication succeeds via the new, separate, corrected
    decision -- early Trust behavior/ordering/semantics are never mutated,
    only a second, additional row is added alongside it."""
    org = _organization(db, "canonical-evidence-preserve-early-trust")
    case_id, run_id = _run_case(db, tmp_path, org.id)
    priorities = analysis_case_command_service.priorities(db, org.id, case_id, run_id=run_id)
    assert [p for p in priorities if p.finding.rule_id == _XDOM_B]

    decisions = list(
        db.scalars(
            select(AnalyticalReadinessDecision).where(
                AnalyticalReadinessDecision.organization_id == org.id,
                AnalyticalReadinessDecision.analytical_level == AnalyticalLevel.ARITHMETIC.value,
            )
        ).all()
    )
    statuses = sorted(d.readiness_status for d in decisions)
    # The original blocked row is still there, untouched, alongside the new
    # corrected one -- never replaced, never mutated in place.
    assert "blocked" in statuses
    assert "ready_with_warnings" in statuses
    blocked_rows = [d for d in decisions if d.readiness_status == "blocked"]
    assert any(d.blocking_rule_codes == ["required_field_completeness"] for d in blocked_rows)
