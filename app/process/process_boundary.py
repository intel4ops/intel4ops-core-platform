from __future__ import annotations

from app.process.activity_type import BoundaryStatus

# ---------------------------------------------------------------------------
# P3.xxE.4 section 11 (test K: partial process -> PARTIAL/censored). Boundary
# classification never assumes a process instance's observed activities are
# its complete lifecycle -- absence of an opening or closing activity type
# is recorded honestly as censoring, never silently treated as COMPLETE.
# ---------------------------------------------------------------------------

_OPENING_ACTIVITY_TYPES = frozenset({"CREATE", "SCHEDULE"})
_CLOSING_ACTIVITY_TYPES = frozenset({"CLOSE", "CANCEL", "COMPLETE"})


def classify_boundary(observed_activity_types: set[str]) -> str:
    """observed_activity_types is the set of named (non-GENERIC) activity
    types actually discovered for one process instance. A process with no
    named activities at all is UNKNOWN -- there is no basis to call it
    censored OR complete."""
    if not observed_activity_types:
        return BoundaryStatus.UNKNOWN.value

    has_opening = bool(observed_activity_types & _OPENING_ACTIVITY_TYPES)
    has_closing = bool(observed_activity_types & _CLOSING_ACTIVITY_TYPES)

    if has_opening and has_closing:
        return BoundaryStatus.COMPLETE.value
    if has_opening and not has_closing:
        return BoundaryStatus.RIGHT_CENSORED.value
    if has_closing and not has_opening:
        return BoundaryStatus.LEFT_CENSORED.value
    return BoundaryStatus.PARTIAL.value
