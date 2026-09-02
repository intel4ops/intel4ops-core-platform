from __future__ import annotations

from dataclasses import dataclass

from app.semantic.review import resolve_effective_decision

# ---------------------------------------------------------------------------
# P3.xxV.2I: canonical event-time evidence for temporal-input Intelligence
# rules. Mirrors app/services/canonical_evidence_completeness.py's shape
# exactly (P3.xxV.2D) -- same authority contract (resolve_effective_decision,
# untouched), same "governed evidence, never raw presence" philosophy -- but
# answers a different question. Fix #3's module asks "is this canonical
# concept satisfied at all" (boolean, for readiness). This module asks
# "which raw field, if any, carries the ACTUAL VALUES a temporal-input rule
# should read" -- because a window-overlap calculation needs the parseable
# datetime series itself, not merely a presence flag.
#
# Framework-free (no pandas import here): returns the WINNING raw field
# name only. Extracting/parsing that field's actual values from a dataframe
# is the caller's job (analysis_case_orchestration_service.py already has
# the canonical_frames dict in scope) -- this module never touches a
# DataFrame, matching app/entities/intelligence_contract.py's own
# "framework-free except the one DB-touching file" convention.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RawTemporalFieldCandidate:
    """One raw field's own machine semantic decision, considered as a
    candidate for a declared canonical temporal concept. Built directly
    from the in-memory SemanticInterpretationOutcome the same run already
    produced (semantic_outcome.decisions_by_case_dataset) -- no DB
    round-trip, matching this codebase's established
    semantic_outcome/entity_candidates threading philosophy."""

    source_field: str
    machine_status: str
    machine_selected_concept: str | None
    machine_confidence: float


@dataclass(frozen=True)
class CanonicalTemporalEvidenceResult:
    satisfied: bool
    # Provenance back to the raw field/value this canonical concept's
    # evidence came from -- never discarded, matching Fix #3's own
    # lineage-preservation requirement.
    source_field: str | None
    semantic_status: str | None
    semantic_confidence: float | None


def resolve_canonical_temporal_evidence(
    temporal_concept: str,
    candidates: list[RawTemporalFieldCandidate],
) -> CanonicalTemporalEvidenceResult:
    """Which raw field (if any) carries AUTHORITATIVE semantic evidence for
    the declared canonical temporal concept -- reuses resolve_effective_decision,
    the exact authority contract Fix #3 and Fix #5 both reused (never a
    second, independently-invented policy): HUMAN_CONFIRMED/HUMAN_CORRECTED/
    AUTO_ACCEPTED grant effective evidence; ACCEPTED_WITH_FLAG and
    REVIEW_REQUIRED do not (unchanged, global policy untouched by this
    module); UNRESOLVED never does.

    Strict concept match only -- a field resolved to a DIFFERENT temporal
    concept (e.g. scheduled_timestamp, completed_timestamp) never silently
    substitutes for the one actually declared, even though both are
    TIMESTAMP-typed. A scheduled or completed time is a different business
    fact than an actual occurrence time; conflating them would let stale or
    wrong evidence answer a window-overlap question that needs the real
    occurrence anchor. No raw field name (event_date, maintenance_date, or
    any other) is ever compared here -- only the concept a field
    independently, semantically resolved to."""
    for candidate in candidates:
        if candidate.machine_selected_concept != temporal_concept:
            continue
        effective = resolve_effective_decision(
            machine_status=candidate.machine_status,
            machine_selected_concept=candidate.machine_selected_concept,
            machine_confidence=candidate.machine_confidence,
            latest_version=None,
        )
        if effective.effective_concept is not None:
            return CanonicalTemporalEvidenceResult(
                satisfied=True,
                source_field=candidate.source_field,
                semantic_status=candidate.machine_status,
                semantic_confidence=candidate.machine_confidence,
            )
    return CanonicalTemporalEvidenceResult(
        satisfied=False, source_field=None, semantic_status=None, semantic_confidence=None
    )
