from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class ValueCategory(StrEnum):
    REVENUE_RECOVERY = "revenue_recovery"
    COST_REDUCTION = "cost_reduction"
    CASH_ACCELERATION = "cash_acceleration"
    MARGIN_PROTECTION = "margin_protection"


class LedgerEntryType(StrEnum):
    VERIFIED_RECOVERY = "verified_recovery"
    ADJUSTMENT_POSITIVE = "adjustment_positive"
    ADJUSTMENT_NEGATIVE = "adjustment_negative"
    REVERSAL = "reversal"
    REINSTATEMENT = "reinstatement"


@dataclass(frozen=True)
class MeasurementInput:
    category: ValueCategory
    baseline_amount: Decimal
    actual_amount: Decimal
    currency_code: str
    days_accelerated: Decimal | None = None
    annual_rate: Decimal | None = None


def calculate_realized_value(value: MeasurementInput) -> Decimal:
    if value.currency_code != value.currency_code.upper() or len(value.currency_code) != 3:
        raise ValueError("currency_code must be a three-letter uppercase code")
    if value.category in {ValueCategory.REVENUE_RECOVERY, ValueCategory.MARGIN_PROTECTION}:
        result = value.actual_amount - value.baseline_amount
    elif value.category == ValueCategory.COST_REDUCTION:
        result = value.baseline_amount - value.actual_amount
    else:
        if value.days_accelerated is None or value.annual_rate is None:
            raise ValueError("cash acceleration requires days_accelerated and annual_rate")
        if value.days_accelerated < 0 or not Decimal("0") <= value.annual_rate <= Decimal("1"):
            raise ValueError("cash acceleration inputs are outside supported bounds")
        result = value.actual_amount * value.annual_rate * value.days_accelerated / Decimal("365")
    return result.quantize(Decimal("0.000000000001"))


def net_verified_value(amounts: list[Decimal]) -> Decimal:
    return sum(amounts, start=Decimal("0")).quantize(Decimal("0.000000000001"))
