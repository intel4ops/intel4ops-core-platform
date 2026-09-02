"""P3.xxV.2I (Fix #6): pure, framework-free unit tests for
resolve_canonical_temporal_evidence -- no DB, no orchestrator, no pandas.
app/services/analysis_case_orchestration_service.py's
_resolve_canonical_temporal_field is the (separately, end-to-end tested)
adapter that builds RawTemporalFieldCandidate from the in-memory
SemanticInterpretationOutcome and calls into this module -- these tests
exercise the authority logic itself directly."""

from app.services.canonical_temporal_evidence import (
    RawTemporalFieldCandidate,
    resolve_canonical_temporal_evidence,
)

_EVENT_TS = "event_timestamp"


def _candidate(
    source_field: str,
    status: str,
    confidence: float,
    selected_concept: str | None,
) -> RawTemporalFieldCandidate:
    return RawTemporalFieldCandidate(
        source_field=source_field,
        machine_status=status,
        machine_selected_concept=selected_concept,
        machine_confidence=confidence,
    )


# --- positive ---


def test_a_exact_canonical_named_field_passes() -> None:
    """A: a raw field already literally named event_date, auto_accepted,
    satisfies the requirement -- pre-existing direct behavior keeps
    working."""
    result = resolve_canonical_temporal_evidence(
        _EVENT_TS,
        [_candidate("event_date", "auto_accepted", 0.98, _EVENT_TS)],
    )
    assert result.satisfied is True
    assert result.source_field == "event_date"


def test_b_authoritative_alias_mapped_field_passes() -> None:
    """B: maintenance_date, resolved to event_timestamp with sufficient
    (auto_accepted) semantic authority, satisfies the requirement -- no
    XDOM-specific branching anywhere in the module being tested."""
    result = resolve_canonical_temporal_evidence(
        _EVENT_TS,
        [_candidate("maintenance_date", "auto_accepted", 0.95, _EVENT_TS)],
    )
    assert result.satisfied is True
    assert result.source_field == "maintenance_date"


def test_c_lineage_is_preserved() -> None:
    result = resolve_canonical_temporal_evidence(
        _EVENT_TS,
        [_candidate("dispatch_date", "auto_accepted", 0.95, _EVENT_TS)],
    )
    assert result.source_field == "dispatch_date"
    assert result.semantic_status == "auto_accepted"
    assert result.semantic_confidence == 0.95


def test_d_human_confirmed_within_the_same_run_is_structurally_inert() -> None:
    """D: matches the established, documented behavior of
    resolve_effective_decision(latest_version=None) everywhere else in this
    codebase (app/entities/entity_resolution.py, Fix #3's own module) --
    HUMAN_CONFIRMED only takes effect via a SemanticDecisionVersion from a
    PRIOR run, which cannot exist within the same run that just produced
    the decision. Not a defect introduced here -- documented, not silently
    assumed."""
    result = resolve_canonical_temporal_evidence(
        _EVENT_TS,
        [_candidate("service_date", "human_confirmed", 1.0, _EVENT_TS)],
    )
    assert result.satisfied is False


# --- negative ---


def test_negative_a_unrelated_concept_never_substitutes() -> None:
    """A: an unrelated date field (e.g. invoice_date resolved to a
    different concept entirely) must not automatically satisfy
    maintenance-event time."""
    result = resolve_canonical_temporal_evidence(
        _EVENT_TS,
        [_candidate("invoice_date", "auto_accepted", 0.95, "cost_amount")],
    )
    assert result.satisfied is False
    assert result.source_field is None


def test_negative_b_missing_evidence_is_insufficient() -> None:
    result = resolve_canonical_temporal_evidence(_EVENT_TS, [])
    assert result.satisfied is False


def test_negative_c_review_required_never_authoritative() -> None:
    """C: REVIEW_REQUIRED temporal evidence is never silently authoritative
    -- global semantic-authority policy is unchanged by this module."""
    result = resolve_canonical_temporal_evidence(
        _EVENT_TS,
        [_candidate("service_date", "review_required", 0.5, _EVENT_TS)],
    )
    assert result.satisfied is False


def test_negative_d_accepted_with_flag_never_authoritative() -> None:
    """D: ACCEPTED_WITH_FLAG (an ambiguous/ceilinged temporal field) is
    documented, not silently promoted -- matches Fix #3's own unchanged
    global policy."""
    result = resolve_canonical_temporal_evidence(
        _EVENT_TS,
        [_candidate("scheduled_date", "accepted_with_flag", 0.8, "scheduled_timestamp")],
    )
    assert result.satisfied is False


def test_negative_e_a_different_temporal_concept_never_silently_substitutes() -> None:
    """E: scheduled_timestamp/completed_timestamp are different business
    facts than event_timestamp (actual occurrence) -- even at
    auto_accepted, a field resolved to a DIFFERENT temporal concept never
    silently answers a declared event_timestamp requirement."""
    result = resolve_canonical_temporal_evidence(
        _EVENT_TS,
        [_candidate("completed_date", "auto_accepted", 0.95, "completed_timestamp")],
    )
    assert result.satisfied is False


def test_negative_f_unresolved_never_authoritative() -> None:
    result = resolve_canonical_temporal_evidence(
        _EVENT_TS,
        [_candidate("maintenance_date", "unresolved", 0.0, None)],
    )
    assert result.satisfied is False


def test_first_authoritative_match_wins_deterministically() -> None:
    """Multiple candidate fields resolved to the same concept -- the
    resolver returns exactly one winner, deterministically the first
    authoritative one encountered, never an arbitrary/unstable choice."""
    result = resolve_canonical_temporal_evidence(
        _EVENT_TS,
        [
            _candidate("event_date", "auto_accepted", 0.98, _EVENT_TS),
            _candidate("maintenance_date", "auto_accepted", 0.95, _EVENT_TS),
        ],
    )
    assert result.source_field == "event_date"
