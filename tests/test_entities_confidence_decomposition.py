"""P3.xxE.3 sections 18/21 + plan review correction 1: relationship
confidence composition. No universal semantic-confidence ceiling; the
weaker side's identity confidence is the floor, structural evidence can
raise it within a bounded contribution, never past the cap."""

from app.entities.confidence_decomposition import (
    ACCEPTED_WITH_FLAG_MIN,
    AUTO_ACCEPT_MIN,
    RELATIONSHIP_CONFIDENCE_CAP,
    compose_relationship_confidence,
    derive_relationship_status,
)
from app.entities.relationship_type import RelationshipStatus


def test_relationship_confidence_never_exceeds_the_cap() -> None:
    confidence = compose_relationship_confidence(
        left_entity_identity_confidence=0.99,
        right_entity_identity_confidence=0.99,
        structural_evidence_confidence=0.95,
    )
    assert confidence.relationship_confidence <= RELATIONSHIP_CONFIDENCE_CAP


def test_weaker_side_is_the_floor() -> None:
    confidence = compose_relationship_confidence(
        left_entity_identity_confidence=0.95,
        right_entity_identity_confidence=0.40,
        structural_evidence_confidence=0.0,
    )
    assert confidence.relationship_confidence >= 0.40
    assert confidence.relationship_confidence < 0.95


def test_structural_evidence_can_raise_confidence_above_the_identity_floor() -> None:
    low_structural = compose_relationship_confidence(
        left_entity_identity_confidence=0.6,
        right_entity_identity_confidence=0.6,
        structural_evidence_confidence=0.0,
    )
    high_structural = compose_relationship_confidence(
        left_entity_identity_confidence=0.6,
        right_entity_identity_confidence=0.6,
        structural_evidence_confidence=0.9,
    )
    assert high_structural.relationship_confidence > low_structural.relationship_confidence
    assert high_structural.relationship_confidence > 0.6


def test_components_are_all_persisted_separately_not_collapsed() -> None:
    confidence = compose_relationship_confidence(
        left_entity_identity_confidence=0.7,
        right_entity_identity_confidence=0.8,
        structural_evidence_confidence=0.5,
    )
    assert confidence.left_entity_identity_confidence == 0.7
    assert confidence.right_entity_identity_confidence == 0.8
    assert confidence.structural_evidence_confidence == 0.5


def test_conflicted_status_bypasses_the_confidence_ladder_entirely() -> None:
    status = derive_relationship_status(relationship_confidence=0.97, has_cardinality_conflict=True)
    assert status == RelationshipStatus.CONFLICTED.value


def test_status_thresholds() -> None:
    assert (
        derive_relationship_status(
            relationship_confidence=AUTO_ACCEPT_MIN, has_cardinality_conflict=False
        )
        == RelationshipStatus.AUTO_ACCEPTED.value
    )
    assert (
        derive_relationship_status(
            relationship_confidence=ACCEPTED_WITH_FLAG_MIN, has_cardinality_conflict=False
        )
        == RelationshipStatus.ACCEPTED_WITH_FLAG.value
    )
    assert (
        derive_relationship_status(relationship_confidence=0.1, has_cardinality_conflict=False)
        == RelationshipStatus.REVIEW_REQUIRED.value
    )
