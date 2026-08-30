from __future__ import annotations

from app.entities.relationship_candidate import RelationshipConfidence
from app.entities.relationship_type import RelationshipStatus

# ---------------------------------------------------------------------------
# P3.xxE.3 sections 18/21: relationship confidence composition
# (plan-review-corrected, correction 1). relationship_confidence is
# composed from BOTH sides' entity_identity_confidence (never
# entity_type_confidence -- whether two records are the same real-world
# entity matters more to link validity than whether the type label is
# exactly right) plus a distinct structural-evidence component. No
# component acts as a blanket ceiling on another the way an earlier draft
# used semantic_confidence as a hard ceiling; each contributes within its
# own evidence class, and the composition is documented here, not a blind
# multiplication of unrelated numbers (that part of the original
# invariant stands -- only the "semantic confidence as universal ceiling"
# mechanism was removed).
# ---------------------------------------------------------------------------

RELATIONSHIP_POLICY_VERSION = "v1"
RELATIONSHIP_CONFIDENCE_CAP = 0.98
_STRUCTURAL_EVIDENCE_WEIGHT = 0.30

AUTO_ACCEPT_MIN = 0.90
ACCEPTED_WITH_FLAG_MIN = 0.70


def compose_relationship_confidence(
    *,
    left_entity_identity_confidence: float,
    right_entity_identity_confidence: float,
    structural_evidence_confidence: float,
) -> RelationshipConfidence:
    """The weaker side's identity confidence is the floor (a relationship
    can't be more trustworthy than the shakier of the two entities it
    connects); independent structural evidence (FK-overlap, co-occurrence,
    cardinality, temporal consistency -- see relationship_discovery.py) can
    raise the result above that floor, within a bounded contribution, never
    past RELATIONSHIP_CONFIDENCE_CAP."""
    identity_floor = min(left_entity_identity_confidence, right_entity_identity_confidence)
    relationship_confidence = min(
        identity_floor + _STRUCTURAL_EVIDENCE_WEIGHT * structural_evidence_confidence,
        RELATIONSHIP_CONFIDENCE_CAP,
    )
    return RelationshipConfidence(
        left_entity_identity_confidence=left_entity_identity_confidence,
        right_entity_identity_confidence=right_entity_identity_confidence,
        structural_evidence_confidence=structural_evidence_confidence,
        relationship_confidence=round(relationship_confidence, 4),
    )


def derive_relationship_status(
    *, relationship_confidence: float, has_cardinality_conflict: bool
) -> str:
    """CONFLICTED is a structural state, bypassing the confidence ladder
    entirely (section 19) -- contradictory cardinality evidence is never
    just "less confident", it's a real conflict requiring review."""
    if has_cardinality_conflict:
        return RelationshipStatus.CONFLICTED.value
    if relationship_confidence >= AUTO_ACCEPT_MIN:
        return RelationshipStatus.AUTO_ACCEPTED.value
    if relationship_confidence >= ACCEPTED_WITH_FLAG_MIN:
        return RelationshipStatus.ACCEPTED_WITH_FLAG.value
    return RelationshipStatus.REVIEW_REQUIRED.value
