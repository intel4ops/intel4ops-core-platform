from datetime import UTC, datetime
from decimal import Decimal

from app.engines.commercial_engine import LimitStatus, evaluate_limit, period_bounds


def test_limit_evaluation_supports_warning_grace_hard_and_read_only() -> None:
    warning = evaluate_limit(Decimal("85"), Decimal("100"), "hard")
    assert warning.status == LimitStatus.WARNING
    assert warning.action == "warn"
    grace = evaluate_limit(Decimal("105"), Decimal("100"), "soft", grace_percentage=Decimal("0.1"))
    assert grace.status == LimitStatus.GRACE
    assert grace.action == "warn"
    blocked = evaluate_limit(Decimal("101"), Decimal("100"), "hard")
    assert blocked.status == LimitStatus.DISABLED
    assert blocked.action == "disabled"
    read_only = evaluate_limit(Decimal("101"), Decimal("100"), "read_only")
    assert read_only.status == LimitStatus.READ_ONLY


def test_period_bounds_are_utc_and_non_overlapping() -> None:
    moment = datetime(2026, 7, 26, 15, 30, tzinfo=UTC)
    day_start, day_end = period_bounds("daily", moment)
    week_start, week_end = period_bounds("weekly", moment)
    month_start, month_end = period_bounds("monthly", moment)
    assert day_start.isoformat() == "2026-07-26T00:00:00+00:00"
    assert (day_end - day_start).days == 1
    assert week_start.weekday() == 0
    assert (week_end - week_start).days == 7
    assert month_start.day == 1
    assert month_end.month == 8
