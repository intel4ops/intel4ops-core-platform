from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# P3.xxE.4 section 5 + plan review correction 3: process-instance-anchor
# discovery. No hard-coded entity-type preference -- every EntityType
# actually present in the run's CanonicalCaseEntity rows is scored the same
# generic way, and the winner is whichever scores highest. WORK_ORDER is
# *expected* to win on the real corpus (baseline: 4193/6696 entities, high
# per-instance discrimination), but that is a predicted outcome of the
# formula, not a rule -- verified directly by the required CUSTOMER-vs-
# WORK_ORDER fixture (correction 3), where CUSTOMER has strictly higher raw
# coverage but loses on instance_granularity_score.
# ---------------------------------------------------------------------------

# Granularity is deliberately the dominant term -- correction 3 requires
# the safeguard to actually be able to flip a real outcome (a high-fan-out
# aggregator type with the broadest raw activity footprint must still
# lose to a better-discriminating type), not merely exist on paper.
_WEIGHT_COVERAGE = 0.15
_WEIGHT_CENTRALITY = 0.15
_WEIGHT_CONNECTIVITY = 0.15
_WEIGHT_GRANULARITY = 0.55

_MIN_ANCHOR_SCORE = 0.05


@dataclass(frozen=True)
class EntityTypeActivityStats:
    """Per-entity-type aggregate stats for one case/run, computed by the
    caller from CanonicalCaseEntity + the activity candidates already
    discovered by activity_discovery.py."""

    entity_type: str
    entity_count: int
    entities_with_activity: int
    total_activity_count: int
    multi_dataset_entity_count: int
    total_entity_count_in_case: int


@dataclass(frozen=True)
class AnchorScore:
    entity_type: str
    coverage_ratio: float
    normalized_centrality: float
    normalized_connectivity: float
    instance_granularity_score: float
    anchor_score: float


def _coverage_ratio(stats: EntityTypeActivityStats, max_activity_count: int) -> float:
    """ "Raw dataset coverage" is the type's raw ACTIVITY/data footprint --
    a high-fan-out aggregator (few CUSTOMER entities, each touching
    thousands of activities) can legitimately have the broadest raw
    coverage despite a low entity_count, which is exactly the scenario
    instance_granularity_score exists to counter-balance (correction 3)."""
    if max_activity_count == 0:
        return 0.0
    return stats.total_activity_count / max_activity_count


def _instance_granularity_score(stats: EntityTypeActivityStats) -> float:
    """Correction 3: 1 / (1 + avg activities per entity of this type).
    Penalizes aggregator types (one CUSTOMER fanning out to thousands of
    activities) even when their raw coverage is broad; favors types where
    each individual entity maps to a small, bounded activity set."""
    if stats.entities_with_activity == 0:
        return 0.0
    avg_activities_per_entity = stats.total_activity_count / stats.entities_with_activity
    return round(1.0 / (1.0 + avg_activities_per_entity), 4)


def _normalized_connectivity(stats: EntityTypeActivityStats) -> float:
    if stats.entity_count == 0:
        return 0.0
    return round(stats.multi_dataset_entity_count / stats.entity_count, 4)


def score_anchor_candidates(
    stats_by_entity_type: list[EntityTypeActivityStats],
) -> list[AnchorScore]:
    """Scores every entity type actually present; entities with zero
    attachable activity are excluded entirely (a type nobody ever performs
    an activity for cannot anchor a process). Centrality is normalized
    against the max entity_count observed across candidate types, so the
    formula never hard-codes an absolute scale."""
    candidates = [s for s in stats_by_entity_type if s.entities_with_activity > 0]
    if not candidates:
        return []

    max_entity_count = max(s.entity_count for s in candidates) or 1
    max_activity_count = max(s.total_activity_count for s in candidates)

    scores: list[AnchorScore] = []
    for stats in candidates:
        coverage_ratio = _coverage_ratio(stats, max_activity_count)
        normalized_centrality = round(stats.entity_count / max_entity_count, 4)
        normalized_connectivity = _normalized_connectivity(stats)
        instance_granularity_score = _instance_granularity_score(stats)
        anchor_score = round(
            _WEIGHT_COVERAGE * coverage_ratio
            + _WEIGHT_CENTRALITY * normalized_centrality
            + _WEIGHT_CONNECTIVITY * normalized_connectivity
            + _WEIGHT_GRANULARITY * instance_granularity_score,
            4,
        )
        scores.append(
            AnchorScore(
                entity_type=stats.entity_type,
                coverage_ratio=round(coverage_ratio, 4),
                normalized_centrality=normalized_centrality,
                normalized_connectivity=normalized_connectivity,
                instance_granularity_score=instance_granularity_score,
                anchor_score=anchor_score,
            )
        )
    return scores


def select_anchor_entity_type(scores: list[AnchorScore]) -> str | None:
    """Argmax with a deterministic alphabetical tiebreak for order
    independence. Returns None (anchorless fallback) when nothing clears
    the minimal threshold -- the concrete mechanism behind an UNKNOWN_PROCESS
    row, not a slogan."""
    eligible = [s for s in scores if s.anchor_score >= _MIN_ANCHOR_SCORE]
    if not eligible:
        return None
    top_score = max(s.anchor_score for s in eligible)
    tied = sorted(s.entity_type for s in eligible if s.anchor_score == top_score)
    return tied[0]
