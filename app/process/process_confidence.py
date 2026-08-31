from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# P3.xxE.4 section 18: CanonicalOperationalProcess-level six-component
# confidence rollup. Mirrors the same never-blind-multiplication philosophy
# as precedence_confidence.py and E.3's confidence_decomposition.py --
# every component persisted separately (see app/models/process_canonical.py),
# this module only computes the six inputs plus the overall rollup used for
# the process row's own top-line confidence.
# ---------------------------------------------------------------------------

_ROLLUP_CAP = 0.98


@dataclass(frozen=True)
class ProcessConfidenceComponents:
    coverage_confidence: float
    activity_confidence: float
    entity_participation_confidence: float
    temporal_confidence: float
    precedence_consistency_confidence: float
    state_transition_confidence: float


def compute_coverage_confidence(*, activities_attached: int, expected_minimum: int = 1) -> float:
    if activities_attached <= 0:
        return 0.0
    return round(min(activities_attached / max(expected_minimum, 1), 1.0) * 0.9 + 0.1, 4)


def compute_process_confidence_components(
    *,
    activity_confidences: list[float],
    participation_confidences: list[float],
    edge_temporal_confidences: list[float],
    edge_precedence_confidences: list[float],
    state_transition_meaning_confidences: list[float],
    activities_attached: int,
) -> ProcessConfidenceComponents:
    """Every list argument is the already-computed per-activity/per-edge
    confidence values for this process instance -- this function only
    averages/aggregates, it never re-derives them (single source of truth
    stays activity_discovery.py / precedence_confidence.py)."""

    def _avg(values: list[float]) -> float:
        return round(sum(values) / len(values), 4) if values else 0.0

    return ProcessConfidenceComponents(
        coverage_confidence=compute_coverage_confidence(activities_attached=activities_attached),
        activity_confidence=_avg(activity_confidences),
        entity_participation_confidence=_avg(participation_confidences),
        temporal_confidence=_avg(edge_temporal_confidences),
        precedence_consistency_confidence=_avg(edge_precedence_confidences),
        state_transition_confidence=_avg(state_transition_meaning_confidences),
    )


def rollup_process_confidence(components: ProcessConfidenceComponents) -> float:
    """Weighted rollup, never a raw product -- an instance with zero
    discovered edges (activity-only evidence) still gets an honest,
    non-zero confidence driven by coverage/activity/participation alone."""
    raw = (
        0.25 * components.coverage_confidence
        + 0.25 * components.activity_confidence
        + 0.15 * components.entity_participation_confidence
        + 0.15 * components.temporal_confidence
        + 0.15 * components.precedence_consistency_confidence
        + 0.05 * components.state_transition_confidence
    )
    return round(min(raw, _ROLLUP_CAP), 4)
