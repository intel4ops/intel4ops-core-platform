from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# P3.xxE.5 plan review correction 2: confidence must never be represented as
# a single max value -- one perfect observation must never make a
# population-level capability READY when the rest of the population is
# low-confidence. ConfidenceDistribution retains the full raw population so
# any aggregation policy (min/median/max/coverage-above-threshold) can be
# computed at evaluation time against whatever threshold a pack declares --
# the threshold is not known when the distribution is built.
# ---------------------------------------------------------------------------

EMPTY_DISTRIBUTION_MEDIAN = 0.0


@dataclass(frozen=True)
class ConfidenceDistribution:
    """values are the raw, unsorted per-observation confidence scores for
    one (type/pair/state) population in one run -- e.g. every
    CanonicalCaseEntity.entity_identity_confidence for entity_type=ASSET."""

    values: tuple[float, ...] = ()

    @property
    def count(self) -> int:
        return len(self.values)

    @property
    def min(self) -> float:
        return min(self.values) if self.values else 0.0

    @property
    def max(self) -> float:
        return max(self.values) if self.values else 0.0

    @property
    def median(self) -> float:
        if not self.values:
            return EMPTY_DISTRIBUTION_MEDIAN
        ordered = sorted(self.values)
        mid = len(ordered) // 2
        if len(ordered) % 2 == 1:
            return ordered[mid]
        return (ordered[mid - 1] + ordered[mid]) / 2

    def coverage_above(self, threshold: float) -> float:
        """Fraction of observations at or above threshold. 0.0 when the
        population is empty -- an empty population can never claim
        coverage, regardless of threshold."""
        if not self.values:
            return 0.0
        return sum(1 for v in self.values if v >= threshold) / len(self.values)


EMPTY_CONFIDENCE_DISTRIBUTION = ConfidenceDistribution()
