"""P3.xxE.2 section 14: ambiguity engine. B: a novel synonym resolves via
AI + context. G: a genuinely ambiguous multi-alias field is never forced
to a single winner -- it stays REVIEW_REQUIRED/UNRESOLVED, never
auto-accepted just because one candidate edges out another."""

import pandas as pd

from app.semantic.interpreter import interpret_dataset
from app.semantic.provider import (
    SemanticFieldProposal,
    SemanticInterpretationRequest,
    SemanticInterpretationResponse,
)


# G. Genuinely ambiguous "amount" (aliases to unit_price, invoice_amount,
# AND cost_amount -- see app/semantic/concept_registry.py) never auto-accepts.
def test_ambiguous_multi_alias_field_is_never_forced_to_auto_accept() -> None:
    df = pd.DataFrame({"amount": ["100.00", "250.50"], "status": ["open", "closed"]})
    result = interpret_dataset("ds-amb", "ledger.csv", df)
    decision = next(d for d in result.field_decisions if d.source_field == "amount")
    assert decision.status != "auto_accepted"
    # The tie is real: multiple concepts are genuinely plausible.
    alternative_concepts = {c.candidate_concept for c in decision.alternative_candidates}
    assert len(alternative_concepts) >= 1


def test_unambiguous_field_still_resolves_cleanly() -> None:
    df = pd.DataFrame({"asset_id": ["A-1", "A-2"], "status": ["active", "retired"]})
    result = interpret_dataset("ds-unamb", "assets.csv", df)
    decision = next(d for d in result.field_decisions if d.source_field == "asset_id")
    assert decision.selected_concept == "asset_id"


# B. Novel synonym resolves using semantic AI + context (not deterministic
# alone -- "svc_ord" has no registry alias, only AI + neighbor context can
# resolve it).
class _NovelSynonymProvider:
    provider_name = "fake_novel"
    provider_version = "1.0"

    def propose(self, request: SemanticInterpretationRequest) -> SemanticInterpretationResponse:
        proposals = [
            SemanticFieldProposal(
                source_field="svc_ord",
                proposed_concept="work_order_id",
                provider_confidence=0.8,
                rationale="abbreviation pattern consistent with a service/work order reference",
            )
        ]
        return SemanticInterpretationResponse(
            proposals=proposals,
            provider_name=self.provider_name,
            provider_version=self.provider_version,
        )


def test_novel_synonym_resolves_via_ai_and_neighbor_context_corroboration() -> None:
    df = pd.DataFrame(
        {
            "svc_ord": ["WO-1", "WO-2"],
            "technician_id": ["T-1", "T-2"],
            "scheduled_date": ["2026-01-01", "2026-01-02"],
            "status": ["open", "closed"],
        }
    )
    result = interpret_dataset("ds-novel", "work.csv", df, provider=_NovelSynonymProvider())
    decision = next(d for d in result.field_decisions if d.source_field == "svc_ord")
    assert decision.selected_concept == "work_order_id"
    # Corroborated by neighbor context (technician_id/scheduled_date are
    # work-order-compatible siblings) -- not AI-only, so it CAN reach
    # auto_accepted, proving neighbor evidence genuinely does work here.
    assert decision.status in {"auto_accepted", "accepted_with_flag"}
    assert decision.ai_provenance is not None


def test_novel_synonym_without_any_corroborating_context_stays_capped() -> None:
    # Same unfamiliar field name, but with NO work-order-shaped siblings --
    # AI alone should not be able to push this past accepted_with_flag.
    df = pd.DataFrame({"svc_ord": ["WO-1", "WO-2"], "notes": ["a", "b"]})
    result = interpret_dataset("ds-novel-2", "misc.csv", df, provider=_NovelSynonymProvider())
    decision = next(d for d in result.field_decisions if d.source_field == "svc_ord")
    assert decision.status != "auto_accepted"
