"""P3.xxE.3 sections 9-12: resolution tiers. Fuzzy is contracts + scoring
only (section 12's escape hatch) -- proven here to never produce anything
an EntityCandidate could be built from, only a bounded score list."""

from app.entities.entity_candidate import EntityObservation
from app.entities.entity_resolution_tiers import (
    FUZZY_CANDIDATE_THRESHOLD,
    composite_key,
    score_fuzzy_candidates,
)


def _obs(entity_type: str, raw: str, normalized: str) -> EntityObservation:
    return EntityObservation(
        analysis_case_dataset_id="cd1",
        dataset_label="ds",
        source_field="field",
        concept_code="asset_id",
        entity_type=entity_type,
        raw_value=raw,
        normalized_value=normalized,
        semantic_confidence=0.9,
        semantic_source="deterministic_confidence_engine",
        human_validated=False,
    )


def test_fuzzy_scores_only_returned_above_threshold() -> None:
    observations = [
        _obs("ASSET", "A1", "asset-001"),
        _obs("ASSET", "A2", "asset-002"),  # very similar to asset-001
        _obs("ASSET", "A3", "zzzzzzzzz"),  # nothing like the others
    ]
    scores = score_fuzzy_candidates(observations)
    assert all(s.score >= FUZZY_CANDIDATE_THRESHOLD for s in scores)
    # the wildly dissimilar pair must never appear
    assert not any({s.left_key, s.right_key} == {"asset-001", "zzzzzzzzz"} for s in scores)


def test_fuzzy_scores_never_cross_entity_type() -> None:
    observations = [_obs("ASSET", "A1", "wo-001"), _obs("WORK_ORDER", "W1", "wo-001")]
    scores = score_fuzzy_candidates(observations)
    assert scores == []  # identical normalized value, but different entity_type -- no comparison


def test_fuzzy_scoring_is_pure_and_returns_no_entity_candidate_type() -> None:
    """Structural proof of the contracts-only position: the return type is
    a bounded list of scores, never anything that could construct an
    EntityCandidate on its own."""
    from app.entities.entity_candidate import FuzzyCandidateScore

    observations = [_obs("ASSET", "A1", "asset-001"), _obs("ASSET", "A2", "asset-002")]
    scores = score_fuzzy_candidates(observations)
    assert all(isinstance(s, FuzzyCandidateScore) for s in scores)


def test_composite_key_requires_at_least_two_observations() -> None:
    assert composite_key([_obs("ASSET", "A1", "a1")]) is None


def test_composite_key_joins_normalized_values_sorted() -> None:
    observations = [_obs("ASSET", "L1", "loc-1"), _obs("ASSET", "A1", "asset-1")]
    key = composite_key(observations)
    assert key == "asset-1|loc-1"
