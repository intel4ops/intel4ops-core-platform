from __future__ import annotations

from dataclasses import dataclass

from app.semantic.review import resolve_effective_decision

# ---------------------------------------------------------------------------
# P3.xxI.2: canonical field resolution for the Revenue Amount / Billing
# Variance capability. Mirrors app/services/canonical_temporal_evidence.py's
# shape and authority contract exactly (same resolve_effective_decision
# policy, untouched, no second policy invented) but generalizes beyond
# temporal concepts to any of this capability's required concepts
# (work_order_id, quantity, unit_price, invoice_amount, currency_code).
#
# Deliberately a SEPARATE module from canonical_temporal_evidence.py rather
# than a shared helper -- XDOM-A must stay byte-identical and untouched
# (P3.xxI.2 mission Section 3/29), so this capability never imports from or
# modifies any XDOM-A file, even indirectly through a refactor.
#
# Framework-free (no pandas import here): returns the WINNING raw field name
# only. Extracting/parsing that field's actual values from a dataframe, and
# performing any join/aggregation across datasets, is the caller's job (see
# app/services/revenue_variance_intelligence_service.py).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RawConceptFieldCandidate:
    """One raw field's own machine semantic decision, considered as a
    candidate for a declared canonical concept. Built directly from the
    in-memory SemanticInterpretationOutcome the same run already produced
    (semantic_outcome.decisions_by_case_dataset) -- no DB round-trip."""

    source_field: str
    machine_status: str
    machine_selected_concept: str | None
    machine_confidence: float


@dataclass(frozen=True)
class ResolvedConceptField:
    satisfied: bool
    source_field: str | None
    semantic_status: str | None
    semantic_confidence: float | None


def resolve_canonical_concept_field(
    concept: str,
    candidates: list[RawConceptFieldCandidate],
) -> ResolvedConceptField:
    """Which raw field (if any) on ONE dataset carries AUTHORITATIVE
    semantic evidence for the declared canonical concept -- reuses
    resolve_effective_decision, the same authority contract every prior fix
    reused (HUMAN_CONFIRMED/HUMAN_CORRECTED/AUTO_ACCEPTED grant effective
    evidence; ACCEPTED_WITH_FLAG/REVIEW_REQUIRED do not; UNRESOLVED never
    does -- the global policy is never weakened here to improve recall on
    any specific corpus).

    Strict concept match only -- a field resolved to a DIFFERENT concept
    never silently substitutes for the one actually declared (e.g. a field
    resolved to cost_amount never substitutes for invoice_amount, even
    though both are MONETARY_AMOUNT-typed)."""
    for candidate in candidates:
        if candidate.machine_selected_concept != concept:
            continue
        effective = resolve_effective_decision(
            machine_status=candidate.machine_status,
            machine_selected_concept=candidate.machine_selected_concept,
            machine_confidence=candidate.machine_confidence,
            latest_version=None,
        )
        if effective.effective_concept is not None:
            return ResolvedConceptField(
                satisfied=True,
                source_field=candidate.source_field,
                semantic_status=candidate.machine_status,
                semantic_confidence=candidate.machine_confidence,
            )
    return ResolvedConceptField(
        satisfied=False, source_field=None, semantic_status=None, semantic_confidence=None
    )


# ---------------------------------------------------------------------------
# P3.xxI.2 Section 6: native multi-currency comparability classification.
# Never assumes USD, never invents an FX rate. Four distinct states, all
# named explicitly rather than collapsed into a boolean.
# ---------------------------------------------------------------------------


class CurrencyComparability:
    SAME_KNOWN = "same_known"
    DIFFERENT_KNOWN = "different_known"
    UNKNOWN_BOTH = "unknown_both"
    MIXED_KNOWN_UNKNOWN = "mixed_known_unknown"


def classify_currency_comparability(
    expected_currency: str | None, actual_currency: str | None
) -> str:
    """Neither side ever assumed USD or coerced. Unknown-vs-unknown is a
    real, distinct, weaker-confidence state (both sides genuinely lack
    currency evidence, matching this corpus's own authoring gap -- see
    docs/p3xxv1b-wave1-system-validation-report.md Section N) from
    known-vs-known and from a known/unknown mismatch, which is the one
    combination genuinely unsafe to compare and always blocked."""
    if expected_currency is not None and actual_currency is not None:
        return (
            CurrencyComparability.SAME_KNOWN
            if expected_currency == actual_currency
            else CurrencyComparability.DIFFERENT_KNOWN
        )
    if expected_currency is None and actual_currency is None:
        return CurrencyComparability.UNKNOWN_BOTH
    return CurrencyComparability.MIXED_KNOWN_UNKNOWN


# Comparability states in which a numeric variance may be computed at all.
# DIFFERENT_KNOWN and MIXED_KNOWN_UNKNOWN never produce a definitive
# financial finding -- no FX is ever invented to reconcile them.
COMPARABLE_CURRENCY_STATES = frozenset(
    {CurrencyComparability.SAME_KNOWN, CurrencyComparability.UNKNOWN_BOTH}
)
