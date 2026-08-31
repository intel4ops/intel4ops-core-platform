"""P3.xxE.5: CaseCapabilityIndex must be invariant to the iteration order
of the entities/relationships/activities/edges it's built from -- mirrors
E.3/E.4's own order-independence precedent. Exercised directly against
_canonical_entity_signals-shape aggregation via the pure ConfidenceDistribution
building blocks, since the DB-touching builder itself is exercised via the
real orchestration integration test (test_capability_shadow_stage.py)."""

from app.intelligence_packs.case_capability_index import CaseCapabilityIndex
from app.intelligence_packs.confidence_distribution import ConfidenceDistribution


def _build_from_rows(rows: list[tuple[str, float]]) -> dict[str, ConfidenceDistribution]:
    by_type: dict[str, list[float]] = {}
    for entity_type, confidence in rows:
        by_type.setdefault(entity_type, []).append(confidence)
    return {k: ConfidenceDistribution(tuple(v)) for k, v in by_type.items()}


def test_confidence_aggregation_is_invariant_to_row_order() -> None:
    rows = [("ASSET", 0.9), ("WORK_ORDER", 0.5), ("ASSET", 0.3), ("ASSET", 0.7)]
    forward = _build_from_rows(rows)
    reversed_rows = _build_from_rows(list(reversed(rows)))

    assert set(forward) == set(reversed_rows)
    for entity_type in forward:
        assert forward[entity_type].count == reversed_rows[entity_type].count
        assert forward[entity_type].min == reversed_rows[entity_type].min
        assert forward[entity_type].max == reversed_rows[entity_type].max
        assert forward[entity_type].median == reversed_rows[entity_type].median


def test_index_field_set_is_identical_regardless_of_construction_order() -> None:
    """Content-keyed comparison of the whole index, built with fields
    populated in two different literal orders -- proves the dataclass
    itself carries no order-dependent state."""
    index_a = CaseCapabilityIndex(
        organization_id="org1",
        analysis_case_id="case1",
        run_id="run1",
        available_domains=frozenset({"maintenance", "operations"}),
        canonical_entity_types_present=frozenset({"ASSET", "WORK_ORDER"}),
    )
    index_b = CaseCapabilityIndex(
        canonical_entity_types_present=frozenset({"WORK_ORDER", "ASSET"}),
        available_domains=frozenset({"operations", "maintenance"}),
        run_id="run1",
        analysis_case_id="case1",
        organization_id="org1",
    )
    assert index_a.available_domains == index_b.available_domains
    assert index_a.canonical_entity_types_present == index_b.canonical_entity_types_present
