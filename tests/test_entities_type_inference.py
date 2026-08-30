"""P3.xxE.3 section 7: entity type inference -- semantic-first, never
from raw field names; ambiguity (multi-type concepts) never silently
resolved."""

from dataclasses import replace

from app.entities.entity_type_inference import infer_entity_type
from app.semantic.concept_registry import default_canonical_concept_registry


def test_known_single_type_concept_resolves() -> None:
    assert infer_entity_type("asset_id", default_canonical_concept_registry) == "ASSET"
    assert infer_entity_type("work_order_id", default_canonical_concept_registry) == "WORK_ORDER"


def test_none_effective_concept_returns_none() -> None:
    assert infer_entity_type(None, default_canonical_concept_registry) is None


def test_unknown_concept_code_returns_none() -> None:
    assert infer_entity_type("not_a_real_concept", default_canonical_concept_registry) is None


def test_concept_with_no_compatible_entity_types_returns_none() -> None:
    # event_timestamp has an empty compatible_entity_types set -- a real
    # concept, but not identifier-typed for entity resolution purposes.
    assert infer_entity_type("event_timestamp", default_canonical_concept_registry) is None


def test_inactive_concept_returns_none() -> None:
    concept = default_canonical_concept_registry.get("asset_id")
    assert concept is not None
    inactive_registry = type(default_canonical_concept_registry)()
    inactive_registry.register(replace(concept, active=False))
    assert infer_entity_type("asset_id", inactive_registry) is None


def test_multi_type_ambiguous_concept_returns_none_never_silently_picks_one() -> None:
    concept = default_canonical_concept_registry.get("asset_id")
    assert concept is not None
    ambiguous_registry = type(default_canonical_concept_registry)()
    ambiguous_registry.register(
        replace(concept, compatible_entity_types=frozenset({"ASSET", "PRODUCT"}))
    )
    assert infer_entity_type("asset_id", ambiguous_registry) is None
