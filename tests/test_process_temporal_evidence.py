"""P3.xxE.4 sections 11/12: STRONG/MODERATE/WEAK/NONE temporal-evidence-
tier classification and per-tier confidence."""

from app.process.temporal_evidence import classify_temporal_tier, temporal_confidence_for_tier


def test_strong_tier_requires_at_least_three_same_row_repeats() -> None:
    assert (
        classify_temporal_tier(
            same_row_repeat_count=3,
            cross_dataset_support_count=0,
            cross_dataset_consistency_ratio=0.0,
            has_structural_evidence_only=False,
        )
        == "STRONG"
    )
    assert (
        classify_temporal_tier(
            same_row_repeat_count=2,
            cross_dataset_support_count=0,
            cross_dataset_consistency_ratio=0.0,
            has_structural_evidence_only=False,
        )
        != "STRONG"
    )


def test_moderate_tier_requires_cross_dataset_support_and_high_consistency() -> None:
    assert (
        classify_temporal_tier(
            same_row_repeat_count=0,
            cross_dataset_support_count=4,
            cross_dataset_consistency_ratio=0.8,
            has_structural_evidence_only=False,
        )
        == "MODERATE"
    )
    assert (
        classify_temporal_tier(
            same_row_repeat_count=0,
            cross_dataset_support_count=4,
            cross_dataset_consistency_ratio=0.5,
            has_structural_evidence_only=False,
        )
        != "MODERATE"
    )


def test_weak_tier_is_structural_only_never_alone_sufficient_for_strong() -> None:
    tier = classify_temporal_tier(
        same_row_repeat_count=0,
        cross_dataset_support_count=0,
        cross_dataset_consistency_ratio=0.0,
        has_structural_evidence_only=True,
    )
    assert tier == "WEAK"
    assert temporal_confidence_for_tier("WEAK", support_count=1) < temporal_confidence_for_tier(
        "STRONG", support_count=1
    )


def test_none_tier_when_no_signal_at_all() -> None:
    tier = classify_temporal_tier(
        same_row_repeat_count=0,
        cross_dataset_support_count=0,
        cross_dataset_consistency_ratio=0.0,
        has_structural_evidence_only=False,
    )
    assert tier == "NONE"
    assert temporal_confidence_for_tier("NONE", support_count=5) == 0.0


def test_confidence_never_exceeds_the_tier_cap() -> None:
    assert temporal_confidence_for_tier("STRONG", support_count=100) <= 0.95
    assert temporal_confidence_for_tier("MODERATE", support_count=100) <= 0.75
    assert temporal_confidence_for_tier("WEAK", support_count=100) <= 0.35
