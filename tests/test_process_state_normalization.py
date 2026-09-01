"""P3.xxE.4 plan review correction 1's worked example: status values
A->B->C at REVIEW_REQUIRED tier support the GENERIC, existence-only
conclusion STATE_A->STATE_B->STATE_C, never the NAMED, meaning-bearing
conclusion OPEN->IN_PROGRESS->COMPLETE, unless independently corroborated."""

from datetime import UTC, datetime

from app.process.state_normalization import (
    find_state_sequence,
    lookup_canonical_state,
    normalize_state_value,
)


def _dt(hour: int) -> datetime:
    return datetime(2026, 1, 1, hour, tzinfo=UTC)


def test_auto_accepted_maps_to_canonical_named_state() -> None:
    state_value, existence, meaning = normalize_state_value(
        raw_value="in_progress",
        machine_status="auto_accepted",
        machine_confidence=0.9,
        is_independently_corroborated=False,
    )
    assert state_value == "IN_PROGRESS"
    assert existence == 0.9
    assert meaning == 0.9


def test_review_required_never_independently_names_a_state() -> None:
    """Correction 1's worked example, directly: REVIEW_REQUIRED status
    evidence never independently maps to the named canonical state, even
    when the raw value would otherwise cleanly match an alias."""
    state_value, existence, meaning = normalize_state_value(
        raw_value="completed",
        machine_status="review_required",
        machine_confidence=0.6,
        is_independently_corroborated=True,
    )
    assert state_value == "completed"  # raw value preserved, not "COMPLETED"
    assert meaning == 0.0
    assert existence <= 0.5


def test_accepted_with_flag_uncorroborated_stays_raw_value() -> None:
    state_value, existence, meaning = normalize_state_value(
        raw_value="open",
        machine_status="accepted_with_flag",
        machine_confidence=0.65,
        is_independently_corroborated=False,
    )
    assert state_value == "open"
    assert meaning == 0.0
    assert existence == 0.65


def test_accepted_with_flag_corroborated_names_the_state() -> None:
    state_value, existence, meaning = normalize_state_value(
        raw_value="open",
        machine_status="accepted_with_flag",
        machine_confidence=0.65,
        is_independently_corroborated=True,
    )
    assert state_value == "OPEN"
    assert meaning == 0.65


def test_unknown_raw_value_never_invents_a_canonical_state() -> None:
    state_value, _, meaning = normalize_state_value(
        raw_value="frobnicated",
        machine_status="auto_accepted",
        machine_confidence=0.9,
        is_independently_corroborated=False,
    )
    assert state_value == "frobnicated"
    assert meaning == 0.0


def test_find_state_sequence_collapses_identical_consecutive_values() -> None:
    transitions = find_state_sequence(
        [("OPEN", _dt(8)), ("OPEN", _dt(9)), ("IN_PROGRESS", _dt(10)), ("COMPLETED", _dt(17))]
    )
    assert transitions == [
        ("OPEN", "IN_PROGRESS", _dt(8), _dt(10)),
        ("IN_PROGRESS", "COMPLETED", _dt(10), _dt(17)),
    ]


def test_find_state_sequence_never_invents_intermediate_states() -> None:
    transitions = find_state_sequence([("OPEN", _dt(8)), ("COMPLETED", _dt(17))])
    assert transitions == [("OPEN", "COMPLETED", _dt(8), _dt(17))]


def test_find_state_sequence_requires_at_least_two_observations() -> None:
    assert find_state_sequence([]) == []
    assert find_state_sequence([("OPEN", _dt(8))]) == []


# P3.xxV.2C: lookup_canonical_state -- the deterministic, machine-status-
# independent raw-value lookup XDOM-B (and any future rule) consumes instead
# of a raw source-system literal. Generic alias-table lookup only -- no
# simulation ID, business family, or filename ever appears here.


def test_lookup_canonical_state_completed_variants() -> None:
    for raw in ("completed", "complete", "done", "finished"):
        assert lookup_canonical_state(raw) == "COMPLETED"


def test_lookup_canonical_state_closed_variants() -> None:
    for raw in ("closed", "close"):
        assert lookup_canonical_state(raw) == "CLOSED"


def test_lookup_canonical_state_is_case_and_whitespace_insensitive() -> None:
    assert lookup_canonical_state("CLOSED") == "CLOSED"
    assert lookup_canonical_state("  Closed  ") == "CLOSED"
    assert lookup_canonical_state("In Progress") == "IN_PROGRESS"


def test_lookup_canonical_state_open_in_progress_cancelled_are_not_completed() -> None:
    assert lookup_canonical_state("open") == "OPEN"
    assert lookup_canonical_state("in_progress") == "IN_PROGRESS"
    assert lookup_canonical_state("cancelled") == "CANCELLED"
    assert lookup_canonical_state("canceled") == "CANCELLED"


def test_lookup_canonical_state_unrecognized_value_returns_none() -> None:
    """Arbitrary/unknown status text never fabricates a canonical state --
    the caller's own governance decides what an unmatched value means."""
    assert lookup_canonical_state("frobnicated") is None
    assert lookup_canonical_state("") is None
