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
