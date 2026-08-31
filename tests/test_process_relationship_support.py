"""P3.xxE.4 section 15 (tests O/P): a CanonicalCaseRelationship never by
itself asserts process sequence -- it may only ever RAISE confidence in
an already-temporally-evidenced precedence claim, never manufacture one."""

from app.process.process_relationship_support import (
    RelationshipSupportSignal,
    apply_structural_corroboration,
    relationship_corroborates_pair,
)


def test_relationship_corroborates_pair_requires_the_same_two_entities() -> None:
    signals = [
        RelationshipSupportSignal(
            entity_id_a="wo-1", entity_id_b="a-1", relationship_confidence=0.8
        )
    ]
    assert relationship_corroborates_pair(signals=signals, entity_id_a="wo-1", entity_id_b="a-1")
    assert relationship_corroborates_pair(signals=signals, entity_id_a="a-1", entity_id_b="wo-1")
    assert not relationship_corroborates_pair(
        signals=signals, entity_id_a="wo-1", entity_id_b="a-2"
    )


def test_relationship_type_alone_never_asserts_process_sequence() -> None:
    """Test O: with no temporal evidence at all, a relationship's mere
    existence must never assert PRECEDES -- confidence stays unchanged."""
    boosted = apply_structural_corroboration(
        precedence_confidence=0.3, has_temporal_evidence=False, is_relationship_corroborated=True
    )
    assert boosted == 0.3


def test_entity_type_pair_alone_never_asserts_process_semantics() -> None:
    """Test P: relationship_corroborates_pair requires matching entity
    IDENTITIES, never inferred from entity TYPE alone."""
    signals = [
        RelationshipSupportSignal(
            entity_id_a="wo-1", entity_id_b="a-1", relationship_confidence=0.8
        )
    ]
    # Same TYPES (WORK_ORDER/ASSET-shaped ids) but different actual entities.
    assert not relationship_corroborates_pair(
        signals=signals, entity_id_a="wo-2", entity_id_b="a-2"
    )


def test_relationship_only_raises_an_already_temporally_evidenced_claim() -> None:
    without_temporal = apply_structural_corroboration(
        precedence_confidence=0.5, has_temporal_evidence=False, is_relationship_corroborated=True
    )
    with_temporal = apply_structural_corroboration(
        precedence_confidence=0.5, has_temporal_evidence=True, is_relationship_corroborated=True
    )
    assert without_temporal == 0.5
    assert with_temporal > 0.5


def test_corroboration_boost_never_exceeds_the_cap() -> None:
    boosted = apply_structural_corroboration(
        precedence_confidence=0.97, has_temporal_evidence=True, is_relationship_corroborated=True
    )
    assert boosted <= 0.98
