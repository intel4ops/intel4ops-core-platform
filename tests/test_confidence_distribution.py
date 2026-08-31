"""P3.xxE.5 plan review correction 2: ConfidenceDistribution retains the
full population (count/min/median/max/coverage_above) rather than
collapsing to a single max value."""

from app.intelligence_packs.confidence_distribution import ConfidenceDistribution


def test_empty_distribution_is_safe_and_never_meets_a_positive_threshold() -> None:
    dist = ConfidenceDistribution()
    assert dist.count == 0
    assert dist.min == 0.0
    assert dist.max == 0.0
    assert dist.median == 0.0
    assert dist.coverage_above(0.5) == 0.0


def test_basic_statistics() -> None:
    dist = ConfidenceDistribution((0.2, 0.5, 0.9))
    assert dist.count == 3
    assert dist.min == 0.2
    assert dist.max == 0.9
    assert dist.median == 0.5


def test_median_of_even_length_population_averages_the_middle_two() -> None:
    dist = ConfidenceDistribution((0.2, 0.4, 0.6, 0.8))
    assert dist.median == 0.5


def test_coverage_above_counts_the_fraction_meeting_the_threshold() -> None:
    dist = ConfidenceDistribution((0.9, 0.1, 0.1, 0.1))
    assert dist.coverage_above(0.7) == 0.25
    assert dist.coverage_above(0.05) == 1.0
    assert dist.coverage_above(0.95) == 0.0


def test_one_high_confidence_outlier_does_not_dominate_coverage() -> None:
    """The exact scenario plan review correction 2 named directly."""
    dist = ConfidenceDistribution((0.99,) + (0.05,) * 9)
    assert dist.coverage_above(0.7) < 0.5
