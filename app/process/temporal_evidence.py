from __future__ import annotations

from enum import StrEnum

# ---------------------------------------------------------------------------
# P3.xxE.4 sections 11/12: governed temporal normalization + 3-tier
# temporal-order-evidence strength. Never invents a timezone when absent
# (timezone_source records whether one was actually provided). Never
# treats DataFrame row order as temporal evidence -- only real timestamp
# VALUES ever feed this module.
# ---------------------------------------------------------------------------

TEMPORAL_NORMALIZATION_POLICY_VERSION = "v1"

_MIN_SUPPORT_FOR_STRONG = 3
_MIN_CONSISTENCY_RATIO_FOR_MODERATE = 0.75


class TemporalEvidenceTier(StrEnum):
    STRONG = "STRONG"
    MODERATE = "MODERATE"
    WEAK = "WEAK"
    NONE = "NONE"


# Base temporal_confidence per tier, plus a per-additional-support step and
# a hard cap -- mirrors app/entities/entity_deduplication.py's own
# tier-base + corroboration-step + cap pattern.
_TIER_BASE_CONFIDENCE: dict[str, float] = {
    TemporalEvidenceTier.STRONG.value: 0.75,
    TemporalEvidenceTier.MODERATE.value: 0.50,
    TemporalEvidenceTier.WEAK.value: 0.20,
    TemporalEvidenceTier.NONE.value: 0.0,
}
_TIER_STEP: dict[str, float] = {
    TemporalEvidenceTier.STRONG.value: 0.04,
    TemporalEvidenceTier.MODERATE.value: 0.03,
    TemporalEvidenceTier.WEAK.value: 0.0,
    TemporalEvidenceTier.NONE.value: 0.0,
}
_TIER_CAP: dict[str, float] = {
    TemporalEvidenceTier.STRONG.value: 0.95,
    TemporalEvidenceTier.MODERATE.value: 0.75,
    TemporalEvidenceTier.WEAK.value: 0.35,
    TemporalEvidenceTier.NONE.value: 0.0,
}


def classify_temporal_tier(
    *,
    same_row_repeat_count: int,
    cross_dataset_support_count: int,
    cross_dataset_consistency_ratio: float,
    has_structural_evidence_only: bool,
) -> str:
    """same_row_repeat_count: number of rows where both timestamps came
    from the SAME row for the same entity (direct, repeated, comparable).
    cross_dataset_support_count/consistency_ratio: cross-dataset
    corroboration strength when no single-row proof exists.
    has_structural_evidence_only: True when ordering evidence is purely
    structural (no comparable timestamps at all)."""
    if same_row_repeat_count >= _MIN_SUPPORT_FOR_STRONG:
        return TemporalEvidenceTier.STRONG.value
    if (
        cross_dataset_support_count > 0
        and cross_dataset_consistency_ratio >= _MIN_CONSISTENCY_RATIO_FOR_MODERATE
    ):
        return TemporalEvidenceTier.MODERATE.value
    if has_structural_evidence_only:
        return TemporalEvidenceTier.WEAK.value
    return TemporalEvidenceTier.NONE.value


def temporal_confidence_for_tier(tier: str, support_count: int) -> float:
    base = _TIER_BASE_CONFIDENCE.get(tier, 0.0)
    step = _TIER_STEP.get(tier, 0.0)
    cap = _TIER_CAP.get(tier, 0.0)
    return round(min(base + step * max(support_count - 1, 0), cap), 4)
