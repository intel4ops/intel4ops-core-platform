from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum


class LimitStatus(StrEnum):
    AVAILABLE = "available"
    WARNING = "warning"
    GRACE = "grace"
    READ_ONLY = "read_only"
    DISABLED = "disabled"
    EXPIRED = "expired"


@dataclass(frozen=True)
class LimitResult:
    status: LimitStatus
    action: str
    current_usage: Decimal
    limit_value: Decimal
    remaining: Decimal


def evaluate_limit(
    usage: Decimal,
    limit: Decimal,
    enforcement_type: str,
    *,
    warning_percentage: Decimal = Decimal("0.8"),
    grace_percentage: Decimal = Decimal("0"),
) -> LimitResult:
    if limit < 0 or usage < 0:
        raise ValueError("usage and limit must be non-negative")
    remaining = max(Decimal("0"), limit - usage)
    if usage < limit * warning_percentage:
        return LimitResult(LimitStatus.AVAILABLE, "allow", usage, limit, remaining)
    if usage <= limit:
        return LimitResult(LimitStatus.WARNING, "warn", usage, limit, remaining)
    if usage <= limit * (Decimal("1") + grace_percentage):
        return LimitResult(LimitStatus.GRACE, "warn", usage, limit, remaining)
    action = {
        "hard": ("disabled", LimitStatus.DISABLED),
        "read_only": ("read_only", LimitStatus.READ_ONLY),
        "soft": ("warn", LimitStatus.GRACE),
        "warning": ("warn", LimitStatus.WARNING),
    }.get(enforcement_type, ("disabled", LimitStatus.DISABLED))
    return LimitResult(action[1], action[0], usage, limit, remaining)


def period_bounds(period_type: str, moment: datetime) -> tuple[datetime, datetime]:
    value = moment.astimezone(UTC)
    if period_type == "daily":
        start = value.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=1)
    if period_type == "weekly":
        start = (value - timedelta(days=value.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return start, start + timedelta(days=7)
    if period_type == "monthly":
        start = value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = (
            start.replace(year=start.year + 1, month=1)
            if start.month == 12
            else start.replace(month=start.month + 1)
        )
        return start, end
    raise ValueError("Unsupported period type")
