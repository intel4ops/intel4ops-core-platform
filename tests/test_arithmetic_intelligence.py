from decimal import Decimal

import pytest

from app.engines.arithmetic_engine import (
    ArithmeticEvaluationError,
    ArithmeticEvaluator,
    DivisionByZeroEvaluationError,
)
from app.engines.rule_engine import RuleEvaluator
from app.registries.calculation_registry import default_calculation_registry
from app.registries.rule_registry import default_rule_registry


def test_decimal_calculations_are_exact_and_nulls_are_explicit() -> None:
    registry = default_calculation_registry()
    evaluator = ArithmeticEvaluator()
    records: list[dict[str, object]] = [
        {"amount": "0.10"},
        {"amount": Decimal("0.20")},
        {"amount": None},
    ]

    total = evaluator.execute(registry.get("sum", "1.0"), records, {"field": "amount"})
    average = evaluator.execute(registry.get("average", "1.0"), records, {"field": "amount"})

    assert total.value == Decimal("0.300000")
    assert average.value == Decimal("0.150000")
    assert total.checked_count == 3
    assert total.excluded_count == 1


def test_distinct_count_excludes_only_nulls_not_duplicates() -> None:
    outcome = ArithmeticEvaluator().execute(
        default_calculation_registry().get("distinct_count", "1.0"),
        [{"code": "A"}, {"code": "A"}, {"code": "B"}, {"code": None}],
        {"field": "code"},
    )

    assert outcome.value == Decimal(2)
    assert outcome.checked_count == 4
    assert outcome.excluded_count == 1


@pytest.mark.parametrize("code", ["ratio", "percentage", "percentage_variance"])
def test_division_by_zero_is_rejected(code: str) -> None:
    definition = default_calculation_registry().get(code, "1.0")
    parameters: dict[str, object] = (
        {"actual": 10, "comparison": 0}
        if code == "percentage_variance"
        else {"numerator": 10, "denominator": 0}
    )
    with pytest.raises(DivisionByZeroEvaluationError):
        ArithmeticEvaluator().execute(definition, [], parameters)


def test_invalid_operands_and_empty_aggregates_are_rejected() -> None:
    definition = default_calculation_registry().get("sum", "1.0")
    with pytest.raises(ArithmeticEvaluationError):
        ArithmeticEvaluator().execute(definition, [{"amount": "not-a-number"}], {"field": "amount"})
    with pytest.raises(ArithmeticEvaluationError):
        ArithmeticEvaluator().execute(definition, [{"amount": None}], {"field": "amount"})


def test_deterministic_rules_use_only_registered_operators() -> None:
    registry = default_rule_registry()
    evaluator = RuleEvaluator()

    threshold = evaluator.execute(
        registry.get("threshold_exceeded", "1.0"),
        {"value": "10.00", "threshold": "9.99"},
    )
    outside = evaluator.execute(
        registry.get("outside_range", "1.0"),
        {"value": "11", "lower": "1", "upper": "10"},
    )

    assert threshold.breached is True
    assert outside.breached is True


def test_definition_registries_are_stable_and_sorted() -> None:
    calculations = default_calculation_registry().list()
    rules = default_rule_registry().list()

    assert [(item.code, item.version) for item in calculations] == sorted(
        (item.code, item.version) for item in calculations
    )
    assert [(item.code, item.version) for item in rules] == sorted(
        (item.code, item.version) for item in rules
    )


def test_approved_oikb_seed_library_is_registered_and_deferred_methods_are_absent() -> None:
    registry = default_calculation_registry()
    approved_codes = {
        "SHARED.QUALITY.DIRECT_QUALITY_COST",
        "SHARED.FINANCE.OUTSTANDING_BALANCE",
        "SHARED.FINANCE.DISCOUNT_VARIANCE",
        "SHARED.PROCUREMENT.PURCHASE_PRICE_VARIANCE",
        "SHARED.PROCUREMENT.THREE_WAY_MATCH_DIFFERENCE",
        "SHARED.ASSET.MAINTENANCE_COST_VARIANCE",
        "SHARED.FINANCE.REVENUE_RECONCILIATION",
        "SHARED.FINANCE.BUDGET_VARIANCE",
        "MOBILITY.REVENUE.FAREBOX_RECONCILIATION",
        "MANUFACTURING.MATERIAL.MASS_BALANCE_VARIANCE",
        "OIL_GAS.CUSTODY.CUSTODY_TRANSFER_BALANCE",
        "OIL_GAS.PRODUCTION.NETWORK_ALLOCATION_VARIANCE",
        "UTILITY.WATER.DMA_WATER_BALANCE",
    }

    registered_codes = {definition.code for definition in registry.list()}
    assert approved_codes <= registered_codes
    assert "MINING.QUALITY.GRADE_VALUE_VARIANCE" not in registered_codes
    assert "PORTS.VESSEL.PORT_CALL_DURATION_DECOMPOSITION" not in registered_codes
    assert all(registry.get(code, "1.0.0").domain_owner for code in approved_codes)


def test_approved_oikb_seed_profiles_execute_over_bounded_primitives() -> None:
    registry = default_calculation_registry()
    evaluator = ArithmeticEvaluator()

    direct_cost = evaluator.execute(
        registry.get("SHARED.QUALITY.DIRECT_QUALITY_COST", "1.0.0"),
        [{"direct_cost": "100"}, {"direct_cost": None}, {"direct_cost": "25.50"}],
        {"field": "direct_cost"},
    )
    outstanding = evaluator.execute(
        registry.get("SHARED.FINANCE.OUTSTANDING_BALANCE", "1.0.0"),
        [],
        {"left": "1000", "right": "700"},
    )
    water_balance = evaluator.execute(
        registry.get("UTILITY.WATER.DMA_WATER_BALANCE", "1.0.0"),
        [],
        {"left": "1000", "right": "850"},
    )

    assert direct_cost == type(direct_cost)(Decimal("125.500000"), 3, 1)
    assert outstanding.value == Decimal("300.000000")
    assert water_balance.value == Decimal("150.000000")
