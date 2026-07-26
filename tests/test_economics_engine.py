from decimal import Decimal

import pytest

from app.engines.economics_engine import (
    DEFAULT_WEIGHTS,
    EconomicInput,
    EconomicsError,
    OpportunityStatus,
    PriorityCategory,
    PriorityInput,
    calculate_economics,
    calculate_priority,
    normalize_weights,
    portfolio_included_value,
    require_transition,
)


def test_expected_economics_use_decimal_and_explicit_formulas() -> None:
    result = calculate_economics(
        EconomicInput(
            gross_exposure=Decimal("100000"),
            addressability_rate=Decimal("0.80"),
            recoverability_rate=Decimal("0.75"),
            success_probability=Decimal("0.60"),
            recovery_cost=Decimal("6000"),
            benefit_period_days=180,
        )
    )
    assert result.addressable_exposure == Decimal("80000.000000000000")
    assert result.expected_recoverable_value == Decimal("60000.000000000000")
    assert result.probability_adjusted_value == Decimal("36000.000000000000")
    assert result.expected_net_benefit == Decimal("30000.000000000000")
    assert result.expected_roi == Decimal("5.000000000000")
    assert result.payback_period_days == Decimal("30.000000000000")
    assert result.calculation_version == "1.0"


def test_zero_cost_negative_benefit_and_invalid_rates_are_governed() -> None:
    zero = calculate_economics(
        EconomicInput(
            Decimal("100"),
            Decimal("1"),
            Decimal("1"),
            Decimal("1"),
            Decimal("0"),
        )
    )
    assert zero.expected_roi is None
    assert zero.zero_cost_policy == "roi_not_applicable"
    negative = calculate_economics(
        EconomicInput(
            Decimal("100"),
            Decimal("1"),
            Decimal("0.5"),
            Decimal("0.5"),
            Decimal("30"),
        )
    )
    assert negative.expected_net_benefit == Decimal("-5.000000000000")
    with pytest.raises(EconomicsError):
        calculate_economics(
            EconomicInput(
                Decimal("100"),
                Decimal("1.1"),
                Decimal("1"),
                Decimal("1"),
                Decimal("0"),
            )
        )


def test_priority_is_deterministic_explainable_and_sensitive_to_controls() -> None:
    values = PriorityInput(
        probability_adjusted_value=Decimal("90000"),
        expected_net_benefit=Decimal("80000"),
        expected_roi=Decimal("4"),
        payback_period_days=Decimal("30"),
        urgency_score=Decimal("0.9"),
        confidence_score=Decimal("0.8"),
        feasibility_score=Decimal("0.7"),
        strategic_alignment_score=Decimal("0.6"),
        risk_score=Decimal("0.2"),
    )
    first = calculate_priority(values)
    second = calculate_priority(values)
    assert first == second
    assert first.category in {PriorityCategory.CRITICAL, PriorityCategory.HIGH}
    assert set(first.normalized_factors) == set(first.contributions) == set(first.weights)
    assert sum(Decimal(item) for item in first.weights.values()) == Decimal("1")

    blocked = calculate_priority(PriorityInput(**{**values.__dict__, "dependency_ready": False}))
    assert blocked.category == PriorityCategory.BLOCKED
    assert "DEPENDENCIES_BLOCKED" in blocked.limitations
    low_confidence = calculate_priority(
        PriorityInput(**{**values.__dict__, "confidence_score": Decimal("0.1")})
    )
    assert low_confidence.category == PriorityCategory.INSUFFICIENT_EVIDENCE


def test_weights_overlap_and_transitions_are_governed() -> None:
    normalized = normalize_weights(
        {name: value * Decimal("2") for name, value in DEFAULT_WEIGHTS.items()}
    )
    assert sum(normalized.values()) == Decimal("1")
    assert portfolio_included_value(Decimal("100"), Decimal("0.4"), "included") == Decimal(
        "40.000000000000"
    )
    assert portfolio_included_value(Decimal("100"), Decimal("1"), "excluded") == 0
    require_transition(OpportunityStatus.DRAFT, OpportunityStatus.UNDER_REVIEW)
    with pytest.raises(EconomicsError):
        require_transition(OpportunityStatus.DRAFT, OpportunityStatus.APPROVED_FOR_ACTION)
