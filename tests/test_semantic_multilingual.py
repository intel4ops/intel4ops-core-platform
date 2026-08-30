"""P3.xxE.2 section 16: multilingual semantic generalization. No runtime
language branching anywhere -- (a) the deterministic path resolves via
French/German aliases added as plain registry data
(app/semantic/concept_registry.py), (b) the AI path resolves an unfamiliar
term via a fake provider regardless of language, since the provider only
ever sees compact field context, never language-specific logic in Core."""

import pandas as pd

from app.semantic.interpreter import interpret_dataset
from app.semantic.provider import (
    SemanticFieldProposal,
    SemanticInterpretationRequest,
    SemanticInterpretationResponse,
)


def test_french_alias_resolves_deterministically() -> None:
    df = pd.DataFrame({"numero_commande": ["WO-1", "WO-2"], "status": ["open", "closed"]})
    result = interpret_dataset("ds-fr", "commandes.csv", df)
    decision = next(d for d in result.field_decisions if d.source_field == "numero_commande")
    assert decision.selected_concept == "work_order_id"
    assert decision.decision_source == "deterministic_confidence_engine"


def test_german_alias_resolves_deterministically() -> None:
    df = pd.DataFrame({"bestellnummer": ["WO-1", "WO-2"], "status": ["open", "closed"]})
    result = interpret_dataset("ds-de", "auftraege.csv", df)
    decision = next(d for d in result.field_decisions if d.source_field == "bestellnummer")
    assert decision.selected_concept == "work_order_id"


class _MultilingualFakeProvider:
    provider_name = "fake_multilingual"
    provider_version = "1.0"

    def propose(self, request: SemanticInterpretationRequest) -> SemanticInterpretationResponse:
        # Simulates an AI provider recognizing an unfamiliar, language-
        # agnostic term ("kundennummer" -- German for "customer number")
        # that has NO registry alias at all -- proving the AI path can
        # generalize where the deterministic alias table has no entry,
        # without any language-specific code in Core itself.
        proposals = [
            SemanticFieldProposal(
                source_field="kundennr",
                proposed_concept="customer_id",
                provider_confidence=0.85,
                rationale="German abbreviation for customer number",
            )
        ]
        return SemanticInterpretationResponse(
            proposals=proposals,
            provider_name=self.provider_name,
            provider_version=self.provider_version,
        )


def test_unfamiliar_term_resolves_via_ai_provider_regardless_of_language() -> None:
    df = pd.DataFrame({"kundennr": ["C-1", "C-2"], "region": ["west", "east"]})
    result = interpret_dataset("ds-de-ai", "kunden.csv", df, provider=_MultilingualFakeProvider())
    decision = next(d for d in result.field_decisions if d.source_field == "kundennr")
    # AI-only, uncorroborated -- reaches ACCEPTED_WITH_FLAG (never
    # AUTO_ACCEPTED), per the corroboration policy, but the concept IS
    # surfaced for governance rather than staying silently unresolved.
    assert decision.selected_concept == "customer_id"
    assert decision.status == "accepted_with_flag"
    assert decision.ai_provenance is not None
