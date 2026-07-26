from decimal import Decimal

import pytest

from app.engines.recovery_ledger_engine import (
    MeasurementInput,
    ValueCategory,
    calculate_realized_value,
    net_verified_value,
)


@pytest.mark.parametrize(
    ("category", "baseline", "actual", "expected"),
    [
        (ValueCategory.REVENUE_RECOVERY, "100", "135", "35.000000000000"),
        (ValueCategory.COST_REDUCTION, "100", "72", "28.000000000000"),
        (ValueCategory.MARGIN_PROTECTION, "150", "180", "30.000000000000"),
    ],
)
def test_realized_value_category_semantics(
    category: ValueCategory, baseline: str, actual: str, expected: str
) -> None:
    result = calculate_realized_value(
        MeasurementInput(category, Decimal(baseline), Decimal(actual), "USD")
    )
    assert result == Decimal(expected)


def test_cash_acceleration_is_time_value_not_full_cash_amount() -> None:
    result = calculate_realized_value(
        MeasurementInput(
            ValueCategory.CASH_ACCELERATION,
            Decimal("0"),
            Decimal("100000"),
            "USD",
            days_accelerated=Decimal("30"),
            annual_rate=Decimal("0.12"),
        )
    )
    assert result == Decimal("986.301369863014")


def test_cash_acceleration_requires_governed_inputs() -> None:
    with pytest.raises(ValueError, match="requires"):
        calculate_realized_value(
            MeasurementInput(
                ValueCategory.CASH_ACCELERATION,
                Decimal("0"),
                Decimal("100"),
                "USD",
            )
        )


def test_net_verified_value_preserves_append_only_signs() -> None:
    assert net_verified_value(
        [Decimal("100"), Decimal("15"), Decimal("-5"), Decimal("-40")]
    ) == Decimal("70.000000000000")
