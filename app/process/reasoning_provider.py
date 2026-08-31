from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

# ---------------------------------------------------------------------------
# P3.xxE.4 section 30: provider-agnostic process-reasoning interface,
# mirroring app/semantic/provider.py's own shape exactly. A provider only
# ever PROPOSES candidate activity types / precedence hypotheses -- it
# never writes canonical truth directly, and process interpretation must
# never be MADE DEPENDENT on an LLM (spec's own explicit instruction).
# Inputs are compact summaries only, never a full DataFrame (test Z).
#
# No real backend is wired up this milestone: ships the interface, a
# compact request/response contract, and a NullProcessReasoningProvider
# that always returns zero proposals -- a safe, honest default, matching
# the established E.1 -> E.2 phasing precedent (interface first, real
# provider a full milestone later, if ever).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ActivityReasoningContext:
    """Compact per-activity-candidate summary -- never raw row-level
    content, never a full dataset."""

    concept_code: str
    dataset_role: str
    candidate_activity_type: str
    corroboration_signals: list[str]
    known_activity_types: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ProcessReasoningRequest:
    case_label: str
    anchor_entity_type: str | None
    activities: list[ActivityReasoningContext]


@dataclass(frozen=True)
class ActivityTypeProposal:
    activity_index: int
    proposed_activity_type: str
    provider_confidence: float
    rationale: str


@dataclass(frozen=True)
class ProcessReasoningResponse:
    proposals: list[ActivityTypeProposal]
    provider_name: str
    provider_version: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class ProcessReasoningProvider(Protocol):
    provider_name: str
    provider_version: str

    def propose(self, request: ProcessReasoningRequest) -> ProcessReasoningResponse: ...


class NullProcessReasoningProvider:
    """The default provider: proposes nothing. Every P3.xxE.4 process
    interpretation result is therefore deterministic-evidence-only until a
    real provider is configured -- a correct, honest state, not a
    placeholder bug."""

    provider_name = "null_provider"
    provider_version = "1.0"

    def propose(self, request: ProcessReasoningRequest) -> ProcessReasoningResponse:
        return ProcessReasoningResponse(
            proposals=[], provider_name=self.provider_name, provider_version=self.provider_version
        )


default_process_reasoning_provider: ProcessReasoningProvider = NullProcessReasoningProvider()
