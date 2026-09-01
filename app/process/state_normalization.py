from __future__ import annotations

from datetime import datetime

# ---------------------------------------------------------------------------
# P3.xxE.4 sections 9/10: generic state normalization + state-transition
# discovery. Never hard-codes CLIENT-specific status strings into business
# logic -- the canonical state vocabulary below is a small, generic,
# English-language alias table (same registry-of-data pattern as
# app/semantic/concept_registry.py), not simulation-specific branching.
# Unknown statuses legitimately remain source-specific states.
#
# Plan review correction 1's worked example, implemented precisely: status
# values A->B->C at REVIEW_REQUIRED tier support the GENERIC, existence-
# only conclusion STATE_A->STATE_B->STATE_C, never the NAMED conclusion
# OPEN->IN_PROGRESS->COMPLETE, unless independently corroborated.
# ---------------------------------------------------------------------------

STATE_NORMALIZATION_POLICY_VERSION = "v1"

_HUMAN_TIERS = frozenset({"human_confirmed", "human_corrected"})

# Small, generic, English-language alias table -- data, not code branching.
# Deliberately compact (spec section 9's own example vocabulary).
_CANONICAL_STATE_ALIASES: dict[str, frozenset[str]] = {
    "OPEN": frozenset({"open", "new", "created"}),
    "ASSIGNED": frozenset({"assigned"}),
    "IN_PROGRESS": frozenset({"active", "in_progress", "in progress", "ongoing", "started"}),
    "COMPLETED": frozenset({"completed", "complete", "done", "finished"}),
    "CLOSED": frozenset({"closed", "close"}),
    "CANCELLED": frozenset({"cancelled", "canceled", "voided", "void"}),
}


def _normalize_raw_state_text(raw_value: object) -> str:
    return " ".join(str(raw_value).strip().casefold().split())


def lookup_canonical_state(raw_value: object) -> str | None:
    """Deterministic raw-value -> canonical-state-name lookup against the
    same small, generic alias table _CANONICAL_STATE_ALIASES already uses --
    for callers that already know a column IS a state/status field (e.g. via
    domain/field mapping) and only need the value-level mapping, without the
    machine_status/confidence-tier gating normalize_state_value applies for
    the separate, harder question of whether a field's CONCEPT identity is
    itself confirmed. Returns None (never a fabricated name) when the raw
    value matches no known alias -- the caller's own governance decides what
    an unrecognized value means; this function only ever reports canonical
    identity, never invents one."""
    return _lookup_canonical_state(_normalize_raw_state_text(raw_value))


def _lookup_canonical_state(normalized_raw: str) -> str | None:
    for canonical, aliases in _CANONICAL_STATE_ALIASES.items():
        if normalized_raw in aliases:
            return canonical
    return None


def normalize_state_value(
    *,
    raw_value: object,
    machine_status: str,
    machine_confidence: float,
    is_independently_corroborated: bool,
) -> tuple[str, float, float]:
    """Returns (state_value, state_existence_confidence, state_meaning_confidence).
    state_value is the CANONICAL name only when the evidence tier permits
    naming (HUMAN_CONFIRMED/HUMAN_CORRECTED/AUTO_ACCEPTED, or
    ACCEPTED_WITH_FLAG with independent corroboration); otherwise it stays
    the raw, source-specific value -- existence recorded, meaning not
    claimed."""
    normalized_raw = _normalize_raw_state_text(raw_value)

    if machine_status in _HUMAN_TIERS or machine_status == "auto_accepted":
        state_existence_confidence = machine_confidence
    elif machine_status == "accepted_with_flag":
        state_existence_confidence = machine_confidence
    elif machine_status == "review_required":
        state_existence_confidence = min(machine_confidence, 0.5)
    else:
        state_existence_confidence = 0.0

    can_name = (
        machine_status in _HUMAN_TIERS
        or machine_status == "auto_accepted"
        or (machine_status == "accepted_with_flag" and is_independently_corroborated)
    )
    if can_name:
        canonical = _lookup_canonical_state(normalized_raw)
        if canonical is not None:
            return canonical, round(state_existence_confidence, 4), round(machine_confidence, 4)

    return str(raw_value), round(state_existence_confidence, 4), 0.0


def find_state_sequence(
    time_ordered_states: list[tuple[str, datetime]],
) -> list[tuple[str, str, datetime, datetime]]:
    """Given a list of (state_value, occurred_at) for ONE entity, already
    sorted by the CALLER using real timestamp values (never row order),
    returns consecutive (from_state, to_state, from_time, to_time) pairs
    for genuine state changes only -- identical consecutive values are
    collapsed (not a transition), and no intermediate state is ever
    invented between two observed values."""
    transitions: list[tuple[str, str, datetime, datetime]] = []
    if len(time_ordered_states) < 2:
        return transitions
    previous_state, previous_time = time_ordered_states[0]
    for state, occurred_at in time_ordered_states[1:]:
        if state != previous_state:
            transitions.append((previous_state, state, previous_time, occurred_at))
            previous_state, previous_time = state, occurred_at
    return transitions
