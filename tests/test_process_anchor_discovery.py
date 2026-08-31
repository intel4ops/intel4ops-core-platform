"""P3.xxE.4 plan review correction 3: anchor scoring must penalize low
instance-discrimination, not just raw coverage."""

from app.process.process_anchor_discovery import (
    EntityTypeActivityStats,
    score_anchor_candidates,
    select_anchor_entity_type,
)


def test_customer_higher_raw_coverage_but_work_order_wins_anchor() -> None:
    """Correction 3's required fixture: CUSTOMER has strictly higher raw
    dataset coverage than WORK_ORDER, but WORK_ORDER still wins anchor
    selection because each individual CUSTOMER aggregates far more
    activities than each individual WORK_ORDER does."""
    customer_stats = EntityTypeActivityStats(
        entity_type="CUSTOMER",
        entity_count=50,
        entities_with_activity=50,
        total_activity_count=5000,  # 100 activities per customer on average
        multi_dataset_entity_count=50,
        total_entity_count_in_case=250,
    )
    work_order_stats = EntityTypeActivityStats(
        entity_type="WORK_ORDER",
        entity_count=200,
        entities_with_activity=200,
        total_activity_count=400,  # 2 activities per work order on average
        multi_dataset_entity_count=100,
        total_entity_count_in_case=250,
    )

    scores = score_anchor_candidates([customer_stats, work_order_stats])
    by_type = {s.entity_type: s for s in scores}

    assert by_type["CUSTOMER"].coverage_ratio > by_type["WORK_ORDER"].coverage_ratio
    assert (
        by_type["WORK_ORDER"].instance_granularity_score
        > by_type["CUSTOMER"].instance_granularity_score
    )

    winner = select_anchor_entity_type(scores)
    assert winner == "WORK_ORDER"


def test_entity_types_with_zero_attachable_activity_are_excluded() -> None:
    stats = EntityTypeActivityStats(
        entity_type="LOCATION",
        entity_count=10,
        entities_with_activity=0,
        total_activity_count=0,
        multi_dataset_entity_count=0,
        total_entity_count_in_case=10,
    )
    assert score_anchor_candidates([stats]) == []


def test_no_candidates_returns_none_for_anchorless_fallback() -> None:
    assert select_anchor_entity_type([]) is None


def test_tiebreak_is_deterministic_alphabetical() -> None:
    stats_a = EntityTypeActivityStats(
        entity_type="ZETA",
        entity_count=10,
        entities_with_activity=10,
        total_activity_count=10,
        multi_dataset_entity_count=5,
        total_entity_count_in_case=20,
    )
    stats_b = EntityTypeActivityStats(
        entity_type="ALPHA",
        entity_count=10,
        entities_with_activity=10,
        total_activity_count=10,
        multi_dataset_entity_count=5,
        total_entity_count_in_case=20,
    )
    scores = score_anchor_candidates([stats_a, stats_b])
    assert scores[0].anchor_score == scores[1].anchor_score
    assert select_anchor_entity_type(scores) == "ALPHA"
