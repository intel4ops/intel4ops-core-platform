"""P3.xxE.4 section 17 + section 16's required per-pair contradiction
pass: precedence confidence decomposition (never blind multiplication)
and CONFLICTED reclassification when both directions are independently
supported."""

from app.process.activity_type import ProcessEdgeType, ProcessStatus
from app.process.precedence_confidence import (
    compose_precedence_confidence,
    detect_precedence_cycles,
    is_contradictory,
    resolve_edge_type,
)
from app.process.sequence_discovery import PairTally


def test_zero_support_never_produces_a_confident_edge() -> None:
    tally = PairTally(type_a="COMPLETE", type_b="SCHEDULE")
    result = compose_precedence_confidence(
        tally, weaker_activity_type_confidence=0.9, entity_participation_confidence=0.8
    )
    assert result.precedence_confidence == 0.0
    assert result.status == ProcessStatus.REVIEW_REQUIRED.value


def test_weaker_side_activity_type_confidence_is_the_floor() -> None:
    strong_tally = PairTally(
        type_a="COMPLETE",
        type_b="SCHEDULE",
        b_before_a_count=4,
        same_row_repeat_count=4,
        observation_count=4,
    )
    weak_semantic = compose_precedence_confidence(
        strong_tally, weaker_activity_type_confidence=0.1, entity_participation_confidence=0.8
    )
    strong_semantic = compose_precedence_confidence(
        strong_tally, weaker_activity_type_confidence=0.9, entity_participation_confidence=0.8
    )
    assert weak_semantic.precedence_confidence < strong_semantic.precedence_confidence


def test_contradiction_detected_when_both_directions_independently_supported() -> None:
    tally = PairTally(
        type_a="COMPLETE",
        type_b="SCHEDULE",
        a_before_b_count=3,
        b_before_a_count=3,
        observation_count=6,
    )
    assert is_contradictory(tally)
    result = compose_precedence_confidence(
        tally, weaker_activity_type_confidence=0.9, entity_participation_confidence=0.8
    )
    assert result.status == ProcessStatus.CONFLICTED.value
    assert resolve_edge_type(tally, result.status) == ProcessEdgeType.ORDER_UNRESOLVED.value


def test_shape_agreement_alone_is_not_a_contradiction() -> None:
    """A clean, one-directional pattern (mirrors E.3's own
    _flag_contradictory_many_to_one_pairs precedent) is never falsely
    flagged."""
    tally = PairTally(
        type_a="COMPLETE",
        type_b="SCHEDULE",
        b_before_a_count=4,
        same_row_repeat_count=4,
        observation_count=4,
    )
    assert not is_contradictory(tally)


def test_concurrent_when_same_time_dominates() -> None:
    tally = PairTally(
        type_a="A",
        type_b="B",
        same_time_count=5,
        a_before_b_count=1,
        observation_count=6,
    )
    result = compose_precedence_confidence(
        tally, weaker_activity_type_confidence=0.9, entity_participation_confidence=0.8
    )
    assert resolve_edge_type(tally, result.status) == ProcessEdgeType.CONCURRENT.value


def test_precedes_when_one_direction_clearly_dominates() -> None:
    tally = PairTally(
        type_a="COMPLETE",
        type_b="SCHEDULE",
        b_before_a_count=4,
        same_row_repeat_count=4,
        observation_count=4,
    )
    result = compose_precedence_confidence(
        tally, weaker_activity_type_confidence=0.9, entity_participation_confidence=0.8
    )
    assert resolve_edge_type(tally, result.status) == ProcessEdgeType.PRECEDES.value


def test_components_are_all_persisted_separately_not_collapsed() -> None:
    tally = PairTally(
        type_a="COMPLETE",
        type_b="SCHEDULE",
        b_before_a_count=4,
        same_row_repeat_count=4,
        observation_count=4,
    )
    result = compose_precedence_confidence(
        tally, weaker_activity_type_confidence=0.7, entity_participation_confidence=0.6
    )
    assert result.semantic_confidence == 0.7
    assert result.entity_participation_confidence == 0.6
    assert result.temporal_confidence >= 0.0
    assert result.repetition_confidence >= 0.0
    assert result.consistency_confidence >= 0.0


def test_detect_precedence_cycles_finds_a_simple_two_node_cycle() -> None:
    edges_in_cycles = detect_precedence_cycles([("A", "B"), ("B", "A")])
    assert ("A", "B") in edges_in_cycles
    assert ("B", "A") in edges_in_cycles


def test_detect_precedence_cycles_ignores_a_pure_dag() -> None:
    edges_in_cycles = detect_precedence_cycles([("A", "B"), ("B", "C")])
    assert edges_in_cycles == set()
