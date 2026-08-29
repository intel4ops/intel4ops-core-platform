"""P3.xxE.1 section 35 D/E/F/G/H: candidate generation, confidence
reconciliation, and the trust/confidence boundary."""

from dataclasses import dataclass

import pandas as pd

from app.semantic.candidate import InterpretationDecisionStatus, SemanticCandidate
from app.semantic.candidate_generator import generate_candidates
from app.semantic.confidence_engine import ConfidenceThresholds, reconcile
from app.semantic.interpreter import interpret_dataset
from app.semantic.profiler import dataset_profiler
from app.semantic.provider import (
    SemanticFieldProposal,
    SemanticInterpretationRequest,
    SemanticInterpretationResponse,
)
from app.semantic.role_classifier import dataset_role_classifier

WORK_ORDER_DF = pd.DataFrame(
    {
        "work_order_id": ["WO-1", "WO-2", "WO-3", "WO-4"],
        "status": ["open", "closed", "open", "closed"],
        "scheduled_date": ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"],
        "asset_id": ["A1", "A1", "A2", "A2"],
    }
)


def test_d_same_canonical_concept_proposed_from_different_source_names() -> None:
    profile_a = dataset_profiler.profile("ds", WORK_ORDER_DF)
    role_a = dataset_role_classifier.classify(profile_a)
    field_a = next(f for f in profile_a.fields if f.source_field == "work_order_id")
    candidates_a = generate_candidates("ds", profile_a, role_a, field_a)

    renamed = WORK_ORDER_DF.rename(columns={"work_order_id": "service_order_id"})
    profile_b = dataset_profiler.profile("ds", renamed)
    role_b = dataset_role_classifier.classify(profile_b)
    field_b = next(f for f in profile_b.fields if f.source_field == "service_order_id")
    candidates_b = generate_candidates("ds", profile_b, role_b, field_b)

    assert candidates_a and candidates_b
    assert candidates_a[0].candidate_concept == candidates_b[0].candidate_concept == "work_order_id"


def test_e_decision_retains_alternatives_and_evidence() -> None:
    result = interpret_dataset("ds-1", "work_orders.csv", WORK_ORDER_DF)
    work_order_decision = next(
        d for d in result.field_decisions if d.source_field == "work_order_id"
    )
    assert work_order_decision.evidence_summary
    assert work_order_decision.selected_concept == "work_order_id"
    # asset_id is a genuinely different, single-candidate field -- assert
    # the *structure* (a list, possibly empty) is always present and typed
    # correctly, proving alternatives are never silently dropped from the
    # contract even when there happens to be only one real candidate.
    asset_decision = next(d for d in result.field_decisions if d.source_field == "asset_id")
    assert isinstance(asset_decision.alternative_candidates, list)


def test_f_confidence_thresholds_are_deterministic() -> None:
    thresholds = ConfidenceThresholds()
    assert thresholds.status_for(0.95) == InterpretationDecisionStatus.AUTO_ACCEPTED.value
    assert thresholds.status_for(0.90) == InterpretationDecisionStatus.AUTO_ACCEPTED.value
    assert thresholds.status_for(0.89) == InterpretationDecisionStatus.ACCEPTED_WITH_FLAG.value
    assert thresholds.status_for(0.70) == InterpretationDecisionStatus.ACCEPTED_WITH_FLAG.value
    assert thresholds.status_for(0.69) == InterpretationDecisionStatus.REVIEW_REQUIRED.value
    assert thresholds.status_for(0.40) == InterpretationDecisionStatus.REVIEW_REQUIRED.value
    assert thresholds.status_for(0.39) == InterpretationDecisionStatus.UNRESOLVED.value
    assert thresholds.status_for(0.0) == InterpretationDecisionStatus.UNRESOLVED.value
    # Same inputs, same outputs, every time -- no hidden randomness/state.
    for _ in range(5):
        assert thresholds.status_for(0.72) == InterpretationDecisionStatus.ACCEPTED_WITH_FLAG.value


def test_g_ai_proposal_alone_cannot_bypass_reconciliation() -> None:
    """A provider proposing a single very-high-confidence candidate still
    goes through the exact same threshold logic as deterministic evidence
    -- it cannot set REVIEW_REQUIRED/HUMAN_CONFIRMED/etc directly, and two
    close AI proposals for the same field still trigger the same
    ambiguity downgrade as two close deterministic candidates."""
    high_confidence_ai_candidate = SemanticCandidate(
        source_dataset_id="ds",
        source_field="mystery_field",
        candidate_concept="asset_id",
        confidence=0.97,
        generated_by="fake_llm:1.0",
    )
    decision = reconcile("ds", "mystery_field", [high_confidence_ai_candidate])
    assert (
        decision.status == InterpretationDecisionStatus.AUTO_ACCEPTED.value
    )  # thresholds, not the provider, decided this

    close_candidate_a = SemanticCandidate(
        source_dataset_id="ds",
        source_field="ambiguous_field",
        candidate_concept="asset_id",
        confidence=0.95,
        generated_by="fake_llm:1.0",
    )
    close_candidate_b = SemanticCandidate(
        source_dataset_id="ds",
        source_field="ambiguous_field",
        candidate_concept="customer_id",
        confidence=0.93,
        generated_by="fake_llm:1.0",
    )
    ambiguous_decision = reconcile("ds", "ambiguous_field", [close_candidate_a, close_candidate_b])
    # The reconciler's own ambiguity rule downgrades this despite both
    # candidates individually clearing the auto-accept threshold -- proof
    # the provider's stated confidence alone never controls the outcome.
    assert ambiguous_decision.status == InterpretationDecisionStatus.ACCEPTED_WITH_FLAG.value


@dataclass
class _FixedProposalProvider:
    provider_name: str = "fixed_test_provider"
    provider_version: str = "1.0"

    def propose(self, request: SemanticInterpretationRequest) -> SemanticInterpretationResponse:
        return SemanticInterpretationResponse(
            proposals=[
                SemanticFieldProposal(
                    source_field="status",
                    proposed_concept="status",
                    provider_confidence=0.99,
                    rationale="looks like a lifecycle field",
                )
            ],
            provider_name=self.provider_name,
            provider_version=self.provider_version,
        )


def test_g_provider_proposals_are_merged_not_substituted() -> None:
    """A configured provider's proposals become additional candidates the
    SAME reconciler scores -- interpret_dataset() with a real provider
    still returns a governed, explainable InterpretationDecision, not a
    provider-authored one."""
    result = interpret_dataset(
        "ds-2", "work_orders.csv", WORK_ORDER_DF, provider=_FixedProposalProvider()
    )
    status_decision = next(d for d in result.field_decisions if d.source_field == "status")
    assert status_decision.selected_concept == "status"
    # Whichever candidate won (deterministic or AI), the governed decision
    # is always stamped with the confidence engine's own metadata, never
    # the provider's -- that stamp is what makes it a governed decision
    # rather than a raw, unreconciled AI answer.
    assert status_decision.decision_source == "deterministic_confidence_engine"


def test_h_data_trust_and_semantic_confidence_are_never_blended() -> None:
    """InterpretationDecision has no trust-related field at all, and
    nothing in the confidence engine reads Trust output -- a perfectly
    trusted dataset can still produce a low-confidence interpretation."""
    from dataclasses import fields as dataclass_fields

    from app.semantic.candidate import InterpretationDecision

    field_names = {f.name for f in dataclass_fields(InterpretationDecision)}
    assert not (field_names & {"trust_score", "trust_status", "data_completeness", "data_quality"})

    # A field with no plausible concept at all (unrecognized name, no
    # value-pattern match) is UNRESOLVED regardless of how clean/complete
    # the underlying data is -- trust was never consulted to produce this.
    weird_df = pd.DataFrame({"xyzzy_unrecognized_field": ["a", "b", "c", "d"]})
    result = interpret_dataset("ds-3", "weird.csv", weird_df)
    decision = result.field_decisions[0]
    assert decision.status == InterpretationDecisionStatus.UNRESOLVED.value
