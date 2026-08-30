"""P3.xxE.3 sections 16/17/19 + plan review correction 2: relationship
discovery. Relationship type/cardinality must be evidence-gated, never
inferred from the entity-type pair alone -- the required proof is
test_same_type_pair_produces_different_relationship_type_by_evidence_shape."""

import pandas as pd

from app.entities.case_entity_context import CaseEntityContext
from app.entities.entity_candidate import EntityCandidate, EntityObservation
from app.entities.entity_deduplication import deduplicate
from app.entities.relationship_discovery import discover_relationships_for_case
from app.entities.relationship_type import Cardinality, RelationshipType


def _obs(dataset_id: str, entity_type: str, field: str, raw: str) -> EntityObservation:
    return EntityObservation(
        analysis_case_dataset_id=dataset_id,
        dataset_label=f"ds-{dataset_id}",
        source_field=field,
        concept_code=field,
        entity_type=entity_type,
        raw_value=raw,
        normalized_value=raw.strip().casefold(),
        semantic_confidence=0.9,
        semantic_source="deterministic_confidence_engine",
        human_validated=False,
    )


def _candidates_from_dataset(
    dataset_id: str, df: pd.DataFrame, type_fields: dict[str, str]
) -> list[EntityCandidate]:
    observations = []
    for entity_type, field in type_fields.items():
        for raw in df[field]:
            observations.append(_obs(dataset_id, entity_type, field, str(raw)))
    return deduplicate(CaseEntityContext(observations=observations))


def test_clean_many_to_one_produces_belongs_to() -> None:
    df = pd.DataFrame(
        {
            "invoice_id": ["INV1", "INV2", "INV3"],
            "work_order_id": ["WO1", "WO1", "WO2"],
        }
    )
    candidates = _candidates_from_dataset(
        "cd1", df, {"INVOICE": "invoice_id", "WORK_ORDER": "work_order_id"}
    )
    relationships = discover_relationships_for_case(candidates, {"cd1": df})
    assert len(relationships) == 3
    for r in relationships:
        assert r.relationship_type == RelationshipType.BELONGS_TO.value
        assert r.cardinality == Cardinality.MANY_TO_ONE.value
        # the many side (invoice) is on the left
        assert r.left_entity_type == "INVOICE"
        assert r.right_entity_type == "WORK_ORDER"


def test_many_to_many_produces_associated_with_not_belongs_to() -> None:
    df = pd.DataFrame(
        {
            "invoice_id": ["INV1", "INV1", "INV2", "INV2"],
            "work_order_id": ["WO1", "WO2", "WO1", "WO2"],
        }
    )
    candidates = _candidates_from_dataset(
        "cd1", df, {"INVOICE": "invoice_id", "WORK_ORDER": "work_order_id"}
    )
    relationships = discover_relationships_for_case(candidates, {"cd1": df})
    assert relationships
    for r in relationships:
        assert r.relationship_type == RelationshipType.ASSOCIATED_WITH.value
        assert r.cardinality == Cardinality.MANY_TO_MANY.value


def test_same_type_pair_produces_different_relationship_type_by_evidence_shape() -> None:
    """The required proof (plan review correction 2): entity-type pairs
    never determine relationship type by themselves -- only the actual
    evidence shape does."""
    belongs_to_df = pd.DataFrame(
        {"invoice_id": ["INV1", "INV2", "INV3"], "work_order_id": ["WO1", "WO1", "WO1"]}
    )
    associated_df = pd.DataFrame(
        {"invoice_id": ["INV1", "INV1", "INV2"], "work_order_id": ["WO1", "WO2", "WO1"]}
    )

    belongs_candidates = _candidates_from_dataset(
        "cd1", belongs_to_df, {"INVOICE": "invoice_id", "WORK_ORDER": "work_order_id"}
    )
    associated_candidates = _candidates_from_dataset(
        "cd2", associated_df, {"INVOICE": "invoice_id", "WORK_ORDER": "work_order_id"}
    )

    belongs_rels = discover_relationships_for_case(belongs_candidates, {"cd1": belongs_to_df})
    associated_rels = discover_relationships_for_case(associated_candidates, {"cd2": associated_df})

    belongs_types = {r.relationship_type for r in belongs_rels}
    associated_types = {r.relationship_type for r in associated_rels}
    assert belongs_types == {RelationshipType.BELONGS_TO.value}
    assert associated_types != belongs_types


def test_only_real_row_level_pairs_are_emitted_never_a_full_cross_product() -> None:
    df = pd.DataFrame(
        {
            "invoice_id": ["INV1", "INV2", "INV3"],
            "work_order_id": ["WO1", "WO2", "WO3"],
        }
    )
    candidates = _candidates_from_dataset(
        "cd1", df, {"INVOICE": "invoice_id", "WORK_ORDER": "work_order_id"}
    )
    relationships = discover_relationships_for_case(candidates, {"cd1": df})
    # 3 distinct invoices x 3 distinct work orders would be 9 if this were
    # a naive cross-product -- only the 3 real observed pairs must appear.
    assert len(relationships) == 3
    pairs = {(r.left_normalized_key, r.right_normalized_key) for r in relationships}
    assert pairs == {("inv1", "wo1"), ("inv2", "wo2"), ("inv3", "wo3")}


def test_contradictory_cardinality_across_datasets_produces_conflicted() -> None:
    clean_df = pd.DataFrame(
        {"invoice_id": ["INV1", "INV2", "INV3"], "work_order_id": ["WO1", "WO1", "WO1"]}
    )
    contradicting_df = pd.DataFrame(
        {"invoice_id": ["INV1", "INV1", "INV1"], "work_order_id": ["WO1", "WO2", "WO3"]}
    )
    candidates = _candidates_from_dataset(
        "cd1", clean_df, {"INVOICE": "invoice_id", "WORK_ORDER": "work_order_id"}
    ) + _candidates_from_dataset(
        "cd2", contradicting_df, {"INVOICE": "invoice_id", "WORK_ORDER": "work_order_id"}
    )
    # re-dedup across both datasets since the helper dedupes per-call
    all_observations = []
    for c in candidates:
        all_observations.extend(c.observations)
    merged_candidates = deduplicate(CaseEntityContext(observations=all_observations))

    relationships = discover_relationships_for_case(
        merged_candidates, {"cd1": clean_df, "cd2": contradicting_df}
    )
    inv1_rels = [
        r for r in relationships if "inv1" in (r.left_normalized_key, r.right_normalized_key)
    ]
    assert any(r.status == "CONFLICTED" for r in inv1_rels)


def test_no_relationship_between_entities_that_never_co_occurred() -> None:
    df1 = pd.DataFrame({"invoice_id": ["INV1"], "work_order_id": ["WO1"]})
    df2 = pd.DataFrame({"invoice_id": ["INV2"], "customer_id": ["CUST1"]})
    candidates = _candidates_from_dataset(
        "cd1", df1, {"INVOICE": "invoice_id", "WORK_ORDER": "work_order_id"}
    ) + _candidates_from_dataset("cd2", df2, {"INVOICE": "invoice_id", "CUSTOMER": "customer_id"})
    relationships = discover_relationships_for_case(candidates, {"cd1": df1, "cd2": df2})
    # WORK_ORDER (from cd1) and CUSTOMER (from cd2) never co-occur in any dataset
    types_seen = {(r.left_entity_type, r.right_entity_type) for r in relationships}
    assert ("WORK_ORDER", "CUSTOMER") not in types_seen
    assert ("CUSTOMER", "WORK_ORDER") not in types_seen
