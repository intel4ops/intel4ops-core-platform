"""P3.xxE.5 Phase 2: XDOM-B is promoted to GOVERNED activation authority --
its own generic readiness result (already exercised and certified in
tests/test_intelligence_readiness_service.py and
tests/test_shadow_comparison.py) now gates whether the pre-existing
run_lost_activity_to_revenue_gap execution runs at all. XDOM-A is promoted
separately (see tests/test_capability_governed_activation_xdom_a.py for its
own dedicated positive-path certification) -- this file focuses on XDOM-B's
own gate plus the generic failure-safety/audit-trail machinery shared by
both rules. See _GOVERNED_RULE_CODES in analysis_case_orchestration_service.py.

These tests cover the ORCHESTRATION-level gate (does execution actually
happen or not, and is it recorded correctly) -- the readiness evaluator's
own trust-domain semantics (the FIELDMAINT-004/005 root cause) are already
exhaustively unit-tested in test_intelligence_readiness_service.py's
test_unresolved_required_trust_domain_blocks and friends, and re-verified
end-to-end against the real live corpus separately. The BLOCKED fixture
here uses a structurally-missing-field trigger (not literally an
unresolved-Trust trigger) purely because it is the simplest deterministic
way to reach BLOCKED through the full orchestrator -- the gate code path
exercised is identical regardless of which requirement category caused
BLOCKED."""

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analysis_case import AnalysisCaseStageEvent
from app.models.entities import Organization
from app.models.intelligence_activation import IntelligenceActivationDecision
from app.schemas.contracts import OrganizationCreate
from app.services.analysis_case_command_service import analysis_case_command_service
from app.services.analysis_case_orchestration_service import analysis_case_orchestration_service
from app.services.analysis_case_service import AnalysisCaseService, UploadedFile
from app.services.organization_service import OrganizationService
from app.storage.local_storage import LocalFileStorage

_XDOM_B = "XDOM-B-LOST-ACTIVITY-REVENUE-GAP"
_XDOM_A = "XDOM-A-ASSET-FAILURE-LOST-ACTIVITY"

# Reuses the exact fixture proven (in test_capability_shadow_stage.py) to
# reach XDOM-B READY with a real "completed, unmatched" gap -- OE-2 has no
# matching revenue record, so run_lost_activity_to_revenue_gap always
# publishes a real XDOM-B-LOST-ACTIVITY-REVENUE-GAP finding for it here.
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

# BLOCKED fixture: revenue dataset deliberately omitted below (only
# operations uploaded) -- domain:revenue missing -> structurally BLOCKED,
# the simplest reliable way to reach BLOCKED through the real orchestrator.


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
    case = service.create(db, org_id, "Governed Case", "single", actor)
    service.register_artifacts(db, org_id, case.id, files, actor)
    run = analysis_case_orchestration_service.start_run(db, org_id, case.id, actor)
    analysis_case_orchestration_service.execute(db, service.storage, org_id, case.id, run.id, actor)
    return case.id, run.id


def _decisions(db: Session, run_id: UUID) -> list[IntelligenceActivationDecision]:
    return list(
        db.scalars(
            select(IntelligenceActivationDecision).where(
                IntelligenceActivationDecision.run_id == run_id
            )
        ).all()
    )


def test_xdom_b_ready_governed_execution_occurs(db: Session, tmp_path: Path) -> None:
    """A -- governed READY: XDOM-B actually executes, mode is 'governed',
    legacy and governed agree, and a real XDOM-B finding is published."""
    org = _organization(db, "gov-ready")
    case_id, run_id = _run_case(
        db,
        tmp_path,
        org.id,
        [
            UploadedFile("maintenance_events.csv", MAINT_CSV),
            UploadedFile("operations_events.csv", OPERATIONS_CSV),
            UploadedFile("revenue_events.csv", REVENUE_CSV),
        ],
    )
    decisions = {d.rule_code: d for d in _decisions(db, run_id)}
    xdom_b = decisions[_XDOM_B]
    assert xdom_b.mode == "governed"
    assert xdom_b.governed_status == "READY"
    assert xdom_b.legacy_activated is True
    assert xdom_b.agree is True

    priorities = analysis_case_command_service.priorities(db, org.id, case_id, run_id=run_id)
    xdom_b_findings = [p for p in priorities if p.finding.rule_id == _XDOM_B]
    assert xdom_b_findings, "expected a real XDOM-B finding when governed READY"

    stage_events = list(
        db.scalars(
            select(AnalysisCaseStageEvent).where(
                AnalysisCaseStageEvent.run_id == run_id,
                AnalysisCaseStageEvent.stage == "cross_domain_intelligence",
            )
        ).all()
    )
    assert any(e.detail.get("rule") == "XDOM-B" for e in stage_events)


def test_xdom_b_blocked_execution_does_not_occur(db: Session, tmp_path: Path) -> None:
    """B/D/E -- governed BLOCKED (here: missing domain:revenue -- the
    simplest reliable BLOCKED trigger through the full orchestrator; the
    trust-specific BLOCKED case is unit-tested exhaustively elsewhere and
    re-verified live): XDOM-B must not execute, zero XDOM-B findings, and
    the activation decision explains the blocker."""
    org = _organization(db, "gov-blocked")
    case_id, run_id = _run_case(
        db,
        tmp_path,
        org.id,
        [
            UploadedFile("maintenance_events.csv", MAINT_CSV),
            UploadedFile("operations_events.csv", OPERATIONS_CSV),
        ],
    )
    decisions = {d.rule_code: d for d in _decisions(db, run_id)}
    xdom_b = decisions[_XDOM_B]
    assert xdom_b.mode == "governed"
    assert xdom_b.governed_status == "BLOCKED"
    assert xdom_b.governed_missing_summary, "BLOCKED decision must explain the blocker"

    priorities = analysis_case_command_service.priorities(db, org.id, case_id, run_id=run_id)
    xdom_b_findings = [p for p in priorities if p.finding.rule_id == _XDOM_B]
    assert xdom_b_findings == [], "governed BLOCKED must never publish an XDOM-B finding"

    stage_events = list(
        db.scalars(
            select(AnalysisCaseStageEvent).where(
                AnalysisCaseStageEvent.run_id == run_id,
                AnalysisCaseStageEvent.stage == "cross_domain_intelligence",
            )
        ).all()
    )
    assert not any(e.detail.get("rule") == "XDOM-B" for e in stage_events)


def test_xdom_a_governed_blocked_overrides_legacy_activation(db: Session, tmp_path: Path) -> None:
    """XDOM-A is now GOVERNED (see test_capability_governed_activation_xdom_a.py
    for its own positive-path certification). This file's own MAINT_CSV
    fixture repeats a single asset_id ("V1") with no independent-identifier
    sibling column, so E.3's canonical entity resolution never reaches
    AUTO_ACCEPTED for it (see the real semantic contract documented in
    test_capability_governed_activation_xdom_a.py) -- legacy's own simpler
    domain+trust condition WOULD activate XDOM-A here, but the governed
    evaluator correctly stays BLOCKED on missing canonical ASSET evidence.
    Once governed, this disagreement must resolve toward safety: XDOM-A
    must NOT execute, proving promotion actually overrides legacy's more
    permissive check rather than merely observing it."""
    org = _organization(db, "gov-xdom-a-blocked")
    case_id, run_id = _run_case(
        db,
        tmp_path,
        org.id,
        [
            UploadedFile("maintenance_events.csv", MAINT_CSV),
            UploadedFile("operations_events.csv", OPERATIONS_CSV),
            UploadedFile("revenue_events.csv", REVENUE_CSV),
        ],
    )
    decisions = {d.rule_code: d for d in _decisions(db, run_id)}
    xdom_a = decisions[_XDOM_A]
    assert xdom_a.mode == "governed"
    assert xdom_a.legacy_activated is True
    assert xdom_a.governed_status == "BLOCKED"
    assert xdom_a.agree is False

    stage_events = list(
        db.scalars(
            select(AnalysisCaseStageEvent).where(
                AnalysisCaseStageEvent.run_id == run_id,
                AnalysisCaseStageEvent.stage == "cross_domain_intelligence",
            )
        ).all()
    )
    xdom_a_ran = any(e.detail.get("rule") == "XDOM-A" for e in stage_events)
    assert xdom_a_ran is False, "governed BLOCKED must override legacy's own activation"

    priorities = analysis_case_command_service.priorities(db, org.id, case_id, run_id=run_id)
    xdom_a_findings = [p for p in priorities if p.finding.rule_id == _XDOM_A]
    assert xdom_a_findings == []


def test_shadow_comparison_persisted_in_governed_mode(db: Session, tmp_path: Path) -> None:
    """F -- legacy/governed comparison rows remain fully persisted for a
    governed rule, not replaced by a bare pass/fail flag -- the audit trail
    (legacy_activated, legacy_reason, governed_status, missing summary,
    agree) stays available after governance becomes active."""
    org = _organization(db, "gov-audit-trail")
    _, run_id = _run_case(
        db,
        tmp_path,
        org.id,
        [
            UploadedFile("maintenance_events.csv", MAINT_CSV),
            UploadedFile("operations_events.csv", OPERATIONS_CSV),
            UploadedFile("revenue_events.csv", REVENUE_CSV),
        ],
    )
    decisions = {d.rule_code: d for d in _decisions(db, run_id)}
    xdom_b = decisions[_XDOM_B]
    assert xdom_b.legacy_activated is True
    assert xdom_b.legacy_reason
    assert xdom_b.governed_status == "READY"
    assert xdom_b.evidence_summary
    assert isinstance(xdom_b.governed_missing_summary, list)


def test_governed_evaluation_failure_defaults_to_not_activated(
    db: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """N -- if capability evaluation itself raises unexpectedly, the safe
    default is NOT ACTIVATED for every governed rule (XDOM-A and XDOM-B):
    neither must execute, the run must not fail, and the failure must be
    recorded as evidence."""
    import app.services.analysis_case_orchestration_service as orch_module

    def _boom(self: object, *args: object, **kwargs: object) -> dict[str, str]:
        raise RuntimeError("simulated capability evaluation failure")

    monkeypatch.setattr(
        orch_module.AnalysisCaseOrchestrationService,
        "_evaluate_intelligence_capabilities",
        _boom,
    )

    org = _organization(db, "gov-eval-failure")
    case_id, run_id = _run_case(
        db,
        tmp_path,
        org.id,
        [
            UploadedFile("maintenance_events.csv", MAINT_CSV),
            UploadedFile("operations_events.csv", OPERATIONS_CSV),
            UploadedFile("revenue_events.csv", REVENUE_CSV),
        ],
    )

    # no IntelligenceActivationDecision rows at all -- evaluation itself
    # never completed -- but the run still finished (never fails the run).
    assert _decisions(db, run_id) == []

    priorities = analysis_case_command_service.priorities(db, org.id, case_id, run_id=run_id)
    xdom_b_findings = [p for p in priorities if p.finding.rule_id == _XDOM_B]
    xdom_a_findings = [p for p in priorities if p.finding.rule_id == _XDOM_A]
    assert xdom_b_findings == [], "capability-evaluation failure must never fall back to executing"
    assert xdom_a_findings == [], "capability-evaluation failure must never fall back to executing"

    failed_events = list(
        db.scalars(
            select(AnalysisCaseStageEvent).where(
                AnalysisCaseStageEvent.run_id == run_id,
                AnalysisCaseStageEvent.stage == "capability_shadow_evaluation",
                AnalysisCaseStageEvent.status == "failed",
            )
        ).all()
    )
    assert failed_events, "expected the capability-evaluation failure to be recorded as evidence"
