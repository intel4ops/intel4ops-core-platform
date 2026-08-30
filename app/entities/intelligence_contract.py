from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.entities.relationship_type import RelationshipStatus
from app.models.entities_canonical import CanonicalCaseEntity, CanonicalCaseRelationship

# ---------------------------------------------------------------------------
# P3.xxE.3 section: the future downstream-Intelligence read contract.
# Defined, NOT wired into any existing rule this milestone (roadmap: P3.xxE.5
# migrates Intelligence rules toward this contract). This is the one file in
# app/entities/ that necessarily imports SQLAlchemy -- the rest of the
# package stays framework-free like app/semantic/* -- because its whole
# purpose is to be the single, easy-to-find place a future rule calls
# instead of a direct table join.
#
# No existing Intelligence rule file calls these functions this milestone.
# ---------------------------------------------------------------------------

_STATUS_RANK = {
    RelationshipStatus.REVIEW_REQUIRED.value: 0,
    RelationshipStatus.CONFLICTED.value: 0,
    RelationshipStatus.ACCEPTED_WITH_FLAG.value: 1,
    RelationshipStatus.AUTO_ACCEPTED.value: 2,
}


def get_case_entities(
    db: Session,
    organization_id: UUID,
    analysis_case_id: UUID,
    run_id: UUID,
    entity_type: str | None = None,
) -> list[CanonicalCaseEntity]:
    stmt = select(CanonicalCaseEntity).where(
        CanonicalCaseEntity.organization_id == organization_id,
        CanonicalCaseEntity.analysis_case_id == analysis_case_id,
        CanonicalCaseEntity.run_id == run_id,
    )
    if entity_type is not None:
        stmt = stmt.where(CanonicalCaseEntity.entity_type == entity_type)
    return list(db.scalars(stmt).all())


def get_case_relationships(
    db: Session,
    organization_id: UUID,
    analysis_case_id: UUID,
    run_id: UUID,
    relationship_type: str | None = None,
    min_status: str = RelationshipStatus.ACCEPTED_WITH_FLAG.value,
) -> list[CanonicalCaseRelationship]:
    stmt = select(CanonicalCaseRelationship).where(
        CanonicalCaseRelationship.organization_id == organization_id,
        CanonicalCaseRelationship.analysis_case_id == analysis_case_id,
        CanonicalCaseRelationship.run_id == run_id,
    )
    if relationship_type is not None:
        stmt = stmt.where(CanonicalCaseRelationship.relationship_type == relationship_type)
    min_rank = _STATUS_RANK.get(min_status, 1)
    results = db.scalars(stmt).all()
    return [r for r in results if _STATUS_RANK.get(r.status, 0) >= min_rank]
