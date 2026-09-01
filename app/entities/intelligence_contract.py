from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.entities.entity_candidate import EntityCandidate
from app.entities.relationship_type import RelationshipStatus
from app.models.entities_canonical import CanonicalCaseEntity, CanonicalCaseRelationship

# ---------------------------------------------------------------------------
# P3.xxE.3 section: the future downstream-Intelligence read contract.
# get_case_entities/get_case_relationships were defined, not wired into any
# existing rule, in E.3. P3.xxV.2H (Fix #5) is the first rule migration
# this file's own header comment forecast -- XDOM-A now consumes
# eligible_entity_keys() below instead of the legacy exact-string
# app/services/entity_resolution_service.py path (see the P3.xxV.2G
# diagnosis report for why: readiness and execution previously read two
# disconnected entity-identity systems).
#
# get_case_entities/get_case_relationships remain the one place in
# app/entities/ that necessarily imports SQLAlchemy -- the rest of the
# package, including eligible_entity_keys() below, stays framework-free
# like app/semantic/*, operating on the same in-memory EntityCandidate list
# P3.xxE.3's own orchestration stage already produces this run (avoiding a
# redundant DB round-trip, matching this codebase's established
# philosophy for semantic_outcome/entity_candidates threading).
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


def eligible_entity_keys(
    candidates: list[EntityCandidate],
    entity_type: str,
    minimum_identity_confidence: float,
) -> set[str]:
    """P3.xxV.2H (Fix #5): the smallest canonical entity contract a
    PER_ENTITY / candidate-local Intelligence rule needs -- a stable
    entity key that (a) resolved to the declared entity_type and (b)
    individually clears the rule's own declared identity-confidence floor,
    backed by >=1 persisted cross-dataset observation (never a bare label
    with no evidence behind it).

    Returns each candidate's display_label (the original raw identifier
    value, e.g. "A-1"), never normalized_key (casefolded, e.g. "a-1" --
    app/entities/identifier_normalization.py) -- a rule that filters raw
    canonical-frame columns by exact string equality, as XDOM-A's own
    dataframe filtering does, needs the same casing the source data itself
    uses, not the identity-resolution layer's internal grouping key.

    Deliberately per-candidate, not population-wide: a case-global tail of
    single-dataset entities that never clear the bar is excluded here, at
    the source, rather than gating the whole rule via a population
    coverage ratio unrelated to what the rule actually executes against
    (see docs/p3xxv2g-entity-population-coverage-diagnosis-report.md,
    Section F, for the two-disconnected-systems defect this replaces).

    minimum_identity_confidence is always the caller's own declared
    IntelligencePackDefinition.minimum_entity_identity_confidence -- never
    a second, independently-chosen number -- so readiness and execution
    stay provably aligned on the same threshold against the same
    population (Section D)."""
    return {
        candidate.display_label
        for candidate in candidates
        if candidate.entity_type == entity_type
        and candidate.entity_identity_confidence >= minimum_identity_confidence
        and candidate.observations
    }
