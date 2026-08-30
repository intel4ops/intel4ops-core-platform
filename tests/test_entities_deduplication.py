"""P3.xxE.3 section 13 + plan review correction 1: entity deduplication
and the corrected confidence model -- entity_type_confidence and
entity_identity_confidence are independent; strong corroborated identifier
evidence can push identity confidence high even when type confidence was
only moderate."""

from app.entities.case_entity_context import CaseEntityContext
from app.entities.entity_candidate import EntityObservation
from app.entities.entity_deduplication import deduplicate


def _obs(
    dataset_id: str, entity_type: str, raw: str, normalized: str, confidence: float
) -> EntityObservation:
    return EntityObservation(
        analysis_case_dataset_id=dataset_id,
        dataset_label=f"ds-{dataset_id}",
        source_field="work_order_id",
        concept_code="work_order_id",
        entity_type=entity_type,
        raw_value=raw,
        normalized_value=normalized,
        semantic_confidence=confidence,
        semantic_source="deterministic_confidence_engine",
        human_validated=False,
    )


def test_one_candidate_per_entity_type_and_normalized_key() -> None:
    context = CaseEntityContext(
        observations=[
            _obs("cd1", "ASSET", "A1", "a1", 0.9),
            _obs("cd2", "ASSET", "A1", "a1", 0.9),
        ]
    )
    candidates = deduplicate(context)
    assert len(candidates) == 1
    assert len(candidates[0].observations) == 2


def test_never_merges_across_entity_type_even_with_identical_normalized_key() -> None:
    context = CaseEntityContext(
        observations=[
            _obs("cd1", "ASSET", "X1", "x1", 0.9),
            _obs("cd1", "WORK_ORDER", "X1", "x1", 0.9),
        ]
    )
    candidates = deduplicate(context)
    assert len(candidates) == 2
    assert {c.entity_type for c in candidates} == {"ASSET", "WORK_ORDER"}


def test_identity_confidence_can_exceed_type_confidence_under_strong_corroboration() -> None:
    """The plan review's own worked example: moderate semantic confidence
    (0.62) on the type, but an exact identifier corroborated across 5
    datasets -- entity_identity_confidence must be allowed to land well
    above entity_type_confidence, never capped by it."""
    observations = [_obs(f"cd{i}", "WORK_ORDER", "X-REF-1", "x-ref-1", 0.62) for i in range(1, 6)]
    context = CaseEntityContext(observations=observations)
    candidates = deduplicate(context)
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.entity_type_confidence == 0.62
    assert candidate.entity_identity_confidence > candidate.entity_type_confidence
    assert candidate.entity_identity_confidence >= 0.95


def test_single_dataset_observation_has_lower_identity_confidence_than_corroborated() -> None:
    single = deduplicate(CaseEntityContext(observations=[_obs("cd1", "ASSET", "A1", "a1", 0.9)]))[0]
    corroborated = deduplicate(
        CaseEntityContext(
            observations=[_obs(f"cd{i}", "ASSET", "A1", "a1", 0.9) for i in range(1, 4)]
        )
    )[0]
    assert single.entity_identity_confidence < corroborated.entity_identity_confidence


def test_resolution_method_is_exact_when_every_raw_value_identical() -> None:
    context = CaseEntityContext(
        observations=[
            _obs("cd1", "ASSET", "A1", "a1", 0.9),
            _obs("cd2", "ASSET", "A1", "a1", 0.9),
        ]
    )
    assert deduplicate(context)[0].resolution_method == "exact"


def test_resolution_method_is_normalized_when_raw_values_differ() -> None:
    context = CaseEntityContext(
        observations=[
            _obs("cd1", "ASSET", " A1 ", "a1", 0.9),
            _obs("cd2", "ASSET", "a1", "a1", 0.9),
        ]
    )
    assert deduplicate(context)[0].resolution_method == "normalized"
