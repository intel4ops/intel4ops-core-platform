"""P3.xxV.2H (Fix #5): pure unit coverage for
app.entities.intelligence_contract.eligible_entity_keys -- the smallest
canonical entity contract a PER_ENTITY / candidate-local Intelligence rule
needs. Framework-free (no DB) -- EntityCandidate/EntityObservation objects
are hand-built exactly like tests/test_entities_deduplication.py's own
convention."""

from app.entities.entity_candidate import EntityCandidate, EntityObservation
from app.entities.intelligence_contract import eligible_entity_keys

_MIN = 0.70


def _observation(dataset_id: str, entity_type: str = "ASSET") -> EntityObservation:
    return EntityObservation(
        analysis_case_dataset_id=dataset_id,
        dataset_label=f"{dataset_id}.csv",
        source_field="asset_id",
        concept_code="asset_id",
        entity_type=entity_type,
        raw_value="A-1",
        normalized_value="a-1",
        semantic_confidence=0.98,
        semantic_source="deterministic_confidence_engine",
        human_validated=False,
    )


def _candidate(
    key: str,
    entity_type: str,
    confidence: float,
    n_observations: int = 2,
) -> EntityCandidate:
    return EntityCandidate(
        entity_type=entity_type,
        normalized_key=key,
        display_label=key,
        resolution_method="exact",
        observations=[_observation(f"ds-{i}", entity_type) for i in range(n_observations)],
        entity_type_confidence=0.98,
        entity_identity_confidence=confidence,
    )


# --- positive ---


def test_a_asset_above_threshold_with_observations_is_eligible() -> None:
    """A: multi-dataset ASSET, identity confidence >= 0.70, observations
    present -> eligible."""
    candidates = [_candidate("a-1", "ASSET", 0.82)]
    assert eligible_entity_keys(candidates, "ASSET", _MIN) == {"a-1"}


def test_b_multiple_eligible_assets_all_returned_independently() -> None:
    """B: each eligible entity is evaluated independently -- none excludes
    another."""
    candidates = [
        _candidate("a-1", "ASSET", 0.82),
        _candidate("a-2", "ASSET", 0.735),
        _candidate("a-3", "ASSET", 0.99),
    ]
    assert eligible_entity_keys(candidates, "ASSET", _MIN) == {"a-1", "a-2", "a-3"}


def test_c_one_low_confidence_asset_does_not_exclude_an_unrelated_high_confidence_one() -> None:
    """C: a low-confidence entity elsewhere in the candidate list never
    contaminates an independent, high-confidence candidate's own
    eligibility -- proven at the pure-function level (the orchestrator-level
    proof lives in test_capability_governed_activation_xdom_a.py)."""
    candidates = [
        _candidate("a-100", "ASSET", 0.94),
        _candidate("a-999", "ASSET", 0.65),
    ]
    assert eligible_entity_keys(candidates, "ASSET", _MIN) == {"a-100"}


def test_d_only_matching_entity_type_considered() -> None:
    """D: a CUSTOMER at high confidence never leaks into an ASSET query."""
    candidates = [
        _candidate("c-1", "CUSTOMER", 0.99),
        _candidate("a-1", "ASSET", 0.82),
    ]
    assert eligible_entity_keys(candidates, "ASSET", _MIN) == {"a-1"}


# --- negative ---


def test_negative_a_below_threshold_asset_not_eligible() -> None:
    candidates = [_candidate("a-1", "ASSET", 0.65)]
    assert eligible_entity_keys(candidates, "ASSET", _MIN) == set()


def test_negative_b_asset_with_no_observations_not_eligible() -> None:
    """B: identity confidence alone is never sufficient -- required
    observation evidence must also exist. Constructed directly (a
    real orchestrator run never produces this combination) to prove the
    function does not trust a bare confidence number with nothing behind
    it."""
    candidate = EntityCandidate(
        entity_type="ASSET",
        normalized_key="a-1",
        display_label="a-1",
        resolution_method="exact",
        observations=[],
        entity_type_confidence=0.98,
        entity_identity_confidence=0.99,
    )
    assert eligible_entity_keys([candidate], "ASSET", _MIN) == set()


def test_negative_c_same_key_different_entity_type_never_cross_contaminates() -> None:
    """C: the closest real, testable proxy this data model supports for
    'entity collision/ambiguous identity' -- two candidates sharing a raw
    normalized_key but resolved to different entity_type populations never
    bleed into each other's eligible set, regardless of confidence."""
    candidates = [
        _candidate("shared-1", "ASSET", 0.99),
        _candidate("shared-1", "WORK_ORDER", 0.99),
    ]
    assert eligible_entity_keys(candidates, "ASSET", _MIN) == {"shared-1"}
    assert eligible_entity_keys(candidates, "WORK_ORDER", _MIN) == {"shared-1"}


def test_negative_d_case_with_only_low_confidence_assets_yields_empty_set() -> None:
    candidates = [
        _candidate("a-1", "ASSET", 0.65),
        _candidate("a-2", "ASSET", 0.65),
    ]
    assert eligible_entity_keys(candidates, "ASSET", _MIN) == set()


def test_negative_e_no_asset_population_at_all_yields_empty_set() -> None:
    assert eligible_entity_keys([], "ASSET", _MIN) == set()
    candidates = [_candidate("c-1", "CUSTOMER", 0.99)]
    assert eligible_entity_keys(candidates, "ASSET", _MIN) == set()


def test_threshold_is_the_callers_own_declared_value_not_hardcoded() -> None:
    """The function takes minimum_identity_confidence as a parameter --
    proving no 0.70 (or any other value) is hardcoded inside it, which is
    what keeps readiness and execution aligned on whatever the pack itself
    declares."""
    candidates = [_candidate("a-1", "ASSET", 0.5)]
    assert eligible_entity_keys(candidates, "ASSET", 0.4) == {"a-1"}
    assert eligible_entity_keys(candidates, "ASSET", 0.6) == set()
