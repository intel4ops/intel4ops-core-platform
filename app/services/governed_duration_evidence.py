from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

import pandas as pd

# ---------------------------------------------------------------------------
# P3.xxI.3: governed canonical duration / interval evidence. A reusable,
# capability-agnostic primitive -- START TIMESTAMP + END TIMESTAMP +
# governed temporal semantics -> elapsed duration in a governed unit.
# Framework-light (pandas only), mirroring
# app/services/governed_cross_dataset_rate.py's own shape exactly: a
# plain dataclass result, no DB table, no new semantic-concept type.
#
# No filename, tenant, customer, simulation, or industry branch anywhere
# in this module. DECLARED_INTERVAL_PAIRS names only generic canonical
# concepts already registered in app/semantic/concept_registry.py --
# reusable for rental duration, downtime, cycle time, turnaround time,
# response time, service duration, maintenance windows, or utilization
# periods alike, purely because the SAME concept pair (or its sibling
# below) governs all of them.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DurationEndpointPair:
    """One declared, generic (start_concept, end_concept) pair that may
    represent an elapsed-duration interval when BOTH resolve as governed
    evidence. Declared here, never hardcoded per-capability."""

    start_concept: str
    end_concept: str


# event_timestamp ("when an event/activity occurred") paired with
# completed_timestamp ("when it was actually completed") covers dispatch
# -> return, downtime start -> restored, request received -> resolved,
# maintenance opened -> closed. scheduled_timestamp -> completed_timestamp
# is the same shape read as "cycle time" (planned -> actually finished) --
# a genuinely different, separately governed pair, not a fallback for the
# first.
DECLARED_INTERVAL_PAIRS: tuple[DurationEndpointPair, ...] = (
    DurationEndpointPair("event_timestamp", "completed_timestamp"),
    DurationEndpointPair("scheduled_timestamp", "completed_timestamp"),
)

_SECONDS_PER_HOUR = Decimal(3600)
_SECONDS_PER_DAY = Decimal(86400)


@dataclass(frozen=True)
class DerivedDurationEvidence:
    """One governed, derived elapsed-duration observation. Provenance-
    complete by construction: both endpoint concepts, their source
    fields and raw values, the row/subject it was computed from, and the
    exact, UNROUNDED elapsed value in both governed units this
    codebase's rate infrastructure already recognizes (hour, day) -- the
    caller selects whichever matches the resolved rate's own unit;
    neither is ever silently converted into the other (matches
    governed_cross_dataset_rate.py's own unit-equality-only policy, and
    Section 6's explicit "23 hours != 1 day" prohibition on invented
    business rounding)."""

    start_concept: str
    end_concept: str
    start_field: str
    end_field: str
    start_value: pd.Timestamp
    end_value: pd.Timestamp
    elapsed_hours: Decimal
    elapsed_days: Decimal
    row_reference: str


def _parse_timestamp(value: object) -> pd.Timestamp | None:
    """Unparseable or missing -> None (abstain), never a fabricated
    value. Preserves a timezone offset when the raw value carries one;
    a naive value is left naive -- this project's existing timestamp-
    interpretation policy, matching governed_cross_dataset_rate.py's own
    _timestamp() helper exactly. No invented timezone conversion here
    either. A bare date (no time component) parses to that date's
    midnight -- pandas' own deterministic, pre-existing date-only
    semantics, not a new rule introduced by this module."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    parsed = pd.to_datetime(str(value), errors="coerce")
    return None if pd.isna(parsed) else parsed


def _elapsed(start: pd.Timestamp, end: pd.Timestamp) -> tuple[Decimal, Decimal] | None:
    """Returns (elapsed_hours, elapsed_days), or None when the interval
    is invalid (end before start, or the two timestamps are not
    comparable -- e.g. one offset-aware and the other naive, which
    pandas itself refuses to compare; that TypeError is exactly the
    correct abstain signal here, never something to paper over with an
    invented conversion)."""
    try:
        if end < start:
            return None
        delta = end - start
    except TypeError:
        return None
    elapsed_seconds = Decimal(str(delta.total_seconds()))
    if elapsed_seconds < 0:
        return None
    return elapsed_seconds / _SECONDS_PER_HOUR, elapsed_seconds / _SECONDS_PER_DAY


def resolve_row_duration(
    row: pd.Series,
    start_field: str,
    end_field: str,
    start_concept: str,
    end_concept: str,
    row_reference: str,
) -> DerivedDurationEvidence | None:
    """Returns a governed elapsed-duration observation for ONE row, or
    None (abstain) when either endpoint is missing, unparseable, or the
    interval is inverted. Never a fabricated zero --
    NO_GOVERNED_DURATION_EVIDENCE != ZERO, the same temporal-safety
    invariant P3.xxI.2A/2B/2C already established for rate and subject
    resolution, reused here unchanged. Callers are expected to pass only
    GOVERNED field names (already resolved through the strict,
    AUTO_ACCEPTED-only semantic authority path) -- an ambiguous or
    review-required endpoint never reaches this function at all, so
    "ambiguous start/end semantic -> abstain" is enforced by construction
    at the caller, not re-checked here."""
    if start_field not in row.index or end_field not in row.index:
        return None
    start = _parse_timestamp(row[start_field])
    end = _parse_timestamp(row[end_field])
    if start is None or end is None:
        return None
    elapsed = _elapsed(start, end)
    if elapsed is None:
        return None
    elapsed_hours, elapsed_days = elapsed
    return DerivedDurationEvidence(
        start_concept=start_concept,
        end_concept=end_concept,
        start_field=start_field,
        end_field=end_field,
        start_value=start,
        end_value=end,
        elapsed_hours=elapsed_hours,
        elapsed_days=elapsed_days,
        row_reference=row_reference,
    )


def resolve_cross_dataset_duration(
    start_by_subject: Mapping[str, object],
    end_by_subject: Mapping[str, object],
    start_concept: str,
    end_concept: str,
) -> dict[str, DerivedDurationEvidence]:
    """Cross-dataset, subject-linked variant: given two subject-keyed
    maps of raw timestamp values (already joined via a governed subject
    key -- e.g. the same kind of one-hop identifier bridge P3.xxI.2C's
    subject resolution already produces), returns a governed elapsed
    duration for every subject present in BOTH maps whose pair validates.
    A subject present in only one map, or whose pair fails the same
    safety checks resolve_row_duration applies, is silently absent from
    the result (abstain; Section 14I's "missing subject linkage -> no
    cross-subject attribution"), never a fabricated entry."""
    results: dict[str, DerivedDurationEvidence] = {}
    for subject_key, start_raw in start_by_subject.items():
        if subject_key not in end_by_subject:
            continue
        start = _parse_timestamp(start_raw)
        end = _parse_timestamp(end_by_subject[subject_key])
        if start is None or end is None:
            continue
        elapsed = _elapsed(start, end)
        if elapsed is None:
            continue
        elapsed_hours, elapsed_days = elapsed
        results[subject_key] = DerivedDurationEvidence(
            start_concept=start_concept,
            end_concept=end_concept,
            start_field="<cross-dataset>",
            end_field="<cross-dataset>",
            start_value=start,
            end_value=end,
            elapsed_hours=elapsed_hours,
            elapsed_days=elapsed_days,
            row_reference=subject_key,
        )
    return results
