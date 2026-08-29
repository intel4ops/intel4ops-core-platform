from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

# ---------------------------------------------------------------------------
# Section 10/29: provider-agnostic semantic AI interface. A provider only
# ever PROPOSES candidate meanings -- it never writes canonical truth
# directly (app/semantic/confidence_engine.py always reconciles AI
# proposals against deterministic evidence before anything becomes a
# governed InterpretationDecision). Inputs are compact summaries only
# (see SemanticInterpretationRequest) -- never a full dataset and never
# hidden validation ground truth.
#
# No real LLM integration is wired up in P3.xxE.1: this milestone ships
# the interface, a compact request/response contract, and a
# NullSemanticReasoningProvider that always returns zero proposals (a
# safe, honest default -- never a fabricated "AI said so" result). Wiring
# a real provider (e.g. an Anthropic/OpenAI-backed implementation) is
# P3.xxE.2+ work, gated behind this same interface so the rest of the
# pipeline never changes when that happens.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FieldInterpretationContext:
    """Compact per-field summary -- never raw row-level content beyond a
    bounded representative sample (see app/semantic/sampling.py)."""

    source_field: str
    physical_type: str
    sample_values: list[str]
    value_patterns: list[str]
    null_rate: float
    uniqueness_ratio: float
    neighbor_field_names: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SemanticInterpretationRequest:
    dataset_label: str
    dataset_role_hint: str | None
    known_concept_codes: list[str]
    fields: list[FieldInterpretationContext]


@dataclass(frozen=True)
class SemanticFieldProposal:
    source_field: str
    proposed_concept: str
    provider_confidence: float
    rationale: str


@dataclass(frozen=True)
class SemanticInterpretationResponse:
    proposals: list[SemanticFieldProposal]
    provider_name: str
    provider_version: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class SemanticReasoningProvider(Protocol):
    provider_name: str
    provider_version: str

    def propose(self, request: SemanticInterpretationRequest) -> SemanticInterpretationResponse: ...


class NullSemanticReasoningProvider:
    """The default provider: proposes nothing. Every P3.xxE.1 interpretation
    result is therefore deterministic-evidence-only until a real provider
    is configured -- this is a correct, honest state, not a placeholder
    bug (section 10: "AI should PROPOSE semantics" -- absence of a
    configured provider must degrade to "no proposal," never to a fake
    one)."""

    provider_name = "null_provider"
    provider_version = "1.0"

    def propose(self, request: SemanticInterpretationRequest) -> SemanticInterpretationResponse:
        return SemanticInterpretationResponse(
            proposals=[], provider_name=self.provider_name, provider_version=self.provider_version
        )


default_semantic_reasoning_provider: SemanticReasoningProvider = NullSemanticReasoningProvider()
