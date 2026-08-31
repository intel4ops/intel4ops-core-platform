from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.process_canonical import (
    CanonicalOperationalProcess,
    CanonicalProcessActivity,
    CanonicalProcessEdge,
)
from app.process.activity_type import ProcessStatus

# ---------------------------------------------------------------------------
# P3.xxE.4 section: the future downstream-Intelligence read contract.
# Defined, NOT wired into any existing rule this milestone (roadmap: a
# future milestone migrates job_to_cash_engine.py's/cross_domain_intelligence_
# service.py's own hard-coded completion->invoicing->payment sequence
# assumptions toward this contract, once they're ready to consume an
# explicit process graph instead). Mirrors
# app/entities/intelligence_contract.py's own shape exactly -- the one
# file in app/process/ that necessarily imports SQLAlchemy, because its
# whole purpose is to be the single, easy-to-find place a future rule
# calls instead of a direct table join.
#
# No existing Intelligence rule file calls these functions this milestone.
# ---------------------------------------------------------------------------

_STATUS_RANK = {
    ProcessStatus.REVIEW_REQUIRED.value: 0,
    ProcessStatus.CONFLICTED.value: 0,
    ProcessStatus.ACCEPTED_WITH_FLAG.value: 1,
    ProcessStatus.AUTO_ACCEPTED.value: 2,
}


def get_case_processes(
    db: Session,
    organization_id: UUID,
    analysis_case_id: UUID,
    run_id: UUID,
    anchor_entity_type: str | None = None,
) -> list[CanonicalOperationalProcess]:
    stmt = select(CanonicalOperationalProcess).where(
        CanonicalOperationalProcess.organization_id == organization_id,
        CanonicalOperationalProcess.analysis_case_id == analysis_case_id,
        CanonicalOperationalProcess.run_id == run_id,
    )
    if anchor_entity_type is not None:
        stmt = stmt.where(CanonicalOperationalProcess.anchor_entity_type == anchor_entity_type)
    return list(db.scalars(stmt).all())


def get_process_activities(
    db: Session,
    organization_id: UUID,
    process_id: UUID,
    activity_type: str | None = None,
) -> list[CanonicalProcessActivity]:
    stmt = select(CanonicalProcessActivity).where(
        CanonicalProcessActivity.organization_id == organization_id,
        CanonicalProcessActivity.process_id == process_id,
    )
    if activity_type is not None:
        stmt = stmt.where(CanonicalProcessActivity.activity_type == activity_type)
    return list(db.scalars(stmt).all())


def get_process_edges(
    db: Session,
    organization_id: UUID,
    process_id: UUID,
    edge_type: str | None = None,
    min_status: str = ProcessStatus.ACCEPTED_WITH_FLAG.value,
) -> list[CanonicalProcessEdge]:
    """min_status filters out REVIEW_REQUIRED/CONFLICTED by default -- a
    future Intelligence rule consuming precedence must opt IN to weaker
    evidence explicitly, never receive it silently (mirrors
    app/entities/intelligence_contract.py::get_case_relationships'
    own default)."""
    stmt = select(CanonicalProcessEdge).where(
        CanonicalProcessEdge.organization_id == organization_id,
        CanonicalProcessEdge.process_id == process_id,
    )
    if edge_type is not None:
        stmt = stmt.where(CanonicalProcessEdge.edge_type == edge_type)
    min_rank = _STATUS_RANK.get(min_status, 1)
    results = db.scalars(stmt).all()
    return [e for e in results if _STATUS_RANK.get(e.status, 0) >= min_rank]
