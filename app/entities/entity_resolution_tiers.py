from __future__ import annotations

import difflib
from enum import StrEnum
from itertools import combinations

from app.entities.entity_candidate import EntityObservation, FuzzyCandidateScore

# ---------------------------------------------------------------------------
# P3.xxE.3 sections 9-12: the four resolution tiers. Algorithm shapes
# (normalization + difflib.SequenceMatcher fuzzy ratio) are reused as
# fresh code from Canonical Mapping's EntityResolutionService -- not
# imported, per the reconciliation decision to stay structurally
# independent of that system's cross-run, org-wide entity master.
#
# EXACT/NORMALIZED collapse into one grouping key in practice
# (normalized_value) -- "exact" is simply the case where every member's
# raw_value was already identical (see entity_deduplication.py). COMPOSITE
# is a mechanism with no live callers this milestone (no compound-
# identifier concept is registered in concept_registry.py yet) --
# documented, not dead code by accident.
#
# FUZZY is contracts + scoring only (section 12's explicit escape hatch):
# scores are computed and returned, but entity_resolution.py never creates
# or merges an EntityCandidate from one. See app/entities/entity_resolution.py.
# ---------------------------------------------------------------------------


class ResolutionTier(StrEnum):
    EXACT = "exact"
    NORMALIZED = "normalized"
    COMPOSITE = "composite"
    FUZZY = "fuzzy"


FUZZY_CANDIDATE_THRESHOLD = 0.75


def composite_key(observations: list[EntityObservation]) -> str | None:
    """AND of normalized-equality across a set of fields belonging to one
    real-world entity -- e.g. (asset_id, location_id) jointly identifying a
    record when neither alone is a stable identifier. Requires 2+
    observations from the SAME dataset (a composite key is only meaningful
    within one record's field set); returns None if fewer than 2 or any
    value is empty after normalization."""
    same_dataset = [o for o in observations if o.normalized_value]
    if len(same_dataset) < 2:
        return None
    return "|".join(sorted(o.normalized_value for o in same_dataset))


def score_fuzzy_candidates(
    observations: list[EntityObservation],
) -> list[FuzzyCandidateScore]:
    """Pairwise difflib.SequenceMatcher ratio between every two distinct
    normalized_value groups of the SAME entity_type. Scores below
    FUZZY_CANDIDATE_THRESHOLD are dropped entirely -- never returned, never
    logged. Scores at/above threshold are returned for observability only;
    see the module docstring."""
    by_type: dict[str, set[str]] = {}
    for obs in observations:
        by_type.setdefault(obs.entity_type, set()).add(obs.normalized_value)

    scores: list[FuzzyCandidateScore] = []
    for entity_type, keys in by_type.items():
        for left, right in combinations(sorted(keys), 2):
            if not left or not right:
                continue
            ratio = round(difflib.SequenceMatcher(None, left, right).ratio(), 4)
            if ratio >= FUZZY_CANDIDATE_THRESHOLD:
                scores.append(
                    FuzzyCandidateScore(
                        entity_type=entity_type,
                        left_key=left,
                        right_key=right,
                        score=ratio,
                        fields_compared=["normalized_value"],
                    )
                )
    return scores
