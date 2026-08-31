"""P3.xxE.4 section 11 (test K: partial process -> PARTIAL/censored)."""

from app.process.activity_type import BoundaryStatus
from app.process.process_boundary import classify_boundary


def test_no_named_activities_is_unknown_not_partial() -> None:
    assert classify_boundary(set()) == BoundaryStatus.UNKNOWN.value


def test_opening_and_closing_present_is_complete() -> None:
    assert classify_boundary({"CREATE", "CLOSE"}) == BoundaryStatus.COMPLETE.value
    assert classify_boundary({"SCHEDULE", "COMPLETE"}) == BoundaryStatus.COMPLETE.value


def test_only_opening_is_right_censored() -> None:
    assert classify_boundary({"CREATE"}) == BoundaryStatus.RIGHT_CENSORED.value


def test_only_closing_is_left_censored() -> None:
    assert classify_boundary({"COMPLETE"}) == BoundaryStatus.LEFT_CENSORED.value


def test_neither_opening_nor_closing_is_partial() -> None:
    assert classify_boundary({"PERFORM", "INSPECT"}) == BoundaryStatus.PARTIAL.value
