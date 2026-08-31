from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.process.temporal_evidence import classify_temporal_tier

# ---------------------------------------------------------------------------
# P3.xxE.4 section 16: pairwise precedence tallying. For each unordered pair
# of DISTINCT activity types attached to the same anchor entity, tallies how
# often A observably precedes B vs. B precedes A vs. same-time vs. unknown
# order -- using actual timestamp VALUES only, never row/dataset processing
# order (test B/C/T). A pair is never forced into a fabricated direction
# when timestamps are equal or one side is missing.
# ---------------------------------------------------------------------------


@dataclass
class PairTally:
    type_a: str
    type_b: str
    a_before_b_count: int = 0
    b_before_a_count: int = 0
    same_time_count: int = 0
    unknown_order_count: int = 0
    same_row_repeat_count: int = 0
    cross_dataset_support_count: int = 0
    observation_count: int = 0

    @property
    def support_count(self) -> int:
        return self.a_before_b_count + self.b_before_a_count + self.same_time_count


@dataclass
class TimedActivity:
    """One activity instance for one anchor entity, ready for pairwise
    comparison. index is the position in the owning process instance's
    ActivityCandidate list (for later edge construction)."""

    index: int
    activity_type: str
    occurred_at: datetime | None
    analysis_case_dataset_id: str
    is_explicit_event: bool


def tally_pairwise_precedence(
    activities: list[TimedActivity],
) -> dict[tuple[str, str], PairTally]:
    """activities are all activities for ONE anchor entity, in ANY order --
    ordering is derived purely from occurred_at values within this
    function, never from list order. Returns tallies keyed by
    (alphabetically-smaller-type, alphabetically-larger-type) for
    determinism regardless of scan order."""
    tallies: dict[tuple[str, str], PairTally] = {}

    for i in range(len(activities)):
        for j in range(i + 1, len(activities)):
            left, right = activities[i], activities[j]
            if left.activity_type == right.activity_type:
                continue

            type_a, type_b = sorted((left.activity_type, right.activity_type))
            key = (type_a, type_b)
            tally = tallies.setdefault(key, PairTally(type_a=type_a, type_b=type_b))
            tally.observation_count += 1

            left_time, right_time = left.occurred_at, right.occurred_at
            if left_time is None or right_time is None:
                tally.unknown_order_count += 1
                continue

            if left.analysis_case_dataset_id == right.analysis_case_dataset_id:
                tally.same_row_repeat_count += 1
            else:
                tally.cross_dataset_support_count += 1

            a_time, b_time = (
                (left_time, right_time) if left.activity_type == type_a else (right_time, left_time)
            )
            if a_time == b_time:
                tally.same_time_count += 1
            elif a_time < b_time:
                tally.a_before_b_count += 1
            else:
                tally.b_before_a_count += 1

    return tallies


def merge_pair_tallies(
    per_entity_tallies: list[dict[tuple[str, str], PairTally]],
) -> dict[tuple[str, str], PairTally]:
    """Aggregates each anchor entity's OWN pairwise tally (computed
    separately per entity by tally_pairwise_precedence -- never pooled
    across entities in one call) into one case-level tally per activity-
    type pair. This is what makes the STRONG tier's "repeating across >=3
    rows" threshold meaningful: same_row_repeat_count only climbs past 3
    when multiple DIFFERENT anchor entities each contribute their own
    same-row observation, mirroring app/entities/relationship_discovery.py's
    own "decide shape once per type-pair at case level, reapply per
    instance" precedent."""
    aggregate: dict[tuple[str, str], PairTally] = {}
    for tallies in per_entity_tallies:
        for key, tally in tallies.items():
            existing = aggregate.get(key)
            if existing is None:
                aggregate[key] = PairTally(
                    type_a=tally.type_a,
                    type_b=tally.type_b,
                    a_before_b_count=tally.a_before_b_count,
                    b_before_a_count=tally.b_before_a_count,
                    same_time_count=tally.same_time_count,
                    unknown_order_count=tally.unknown_order_count,
                    same_row_repeat_count=tally.same_row_repeat_count,
                    cross_dataset_support_count=tally.cross_dataset_support_count,
                    observation_count=tally.observation_count,
                )
                continue
            existing.a_before_b_count += tally.a_before_b_count
            existing.b_before_a_count += tally.b_before_a_count
            existing.same_time_count += tally.same_time_count
            existing.unknown_order_count += tally.unknown_order_count
            existing.same_row_repeat_count += tally.same_row_repeat_count
            existing.cross_dataset_support_count += tally.cross_dataset_support_count
            existing.observation_count += tally.observation_count
    return aggregate


def tally_temporal_evidence_tier(tally: PairTally) -> str:
    consistency_ratio = 0.0
    if tally.support_count > 0:
        consistency_ratio = (
            max(tally.a_before_b_count, tally.b_before_a_count) / tally.support_count
        )
    return classify_temporal_tier(
        same_row_repeat_count=tally.same_row_repeat_count,
        cross_dataset_support_count=tally.cross_dataset_support_count,
        cross_dataset_consistency_ratio=consistency_ratio,
        has_structural_evidence_only=tally.support_count == 0,
    )
