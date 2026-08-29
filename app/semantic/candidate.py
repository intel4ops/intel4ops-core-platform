from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from app.models.entities import utc_now

# ---------------------------------------------------------------------------
# Sections 6/7: ephemeral candidate generation + the governed decision made
# from it. Candidates are cheap, in-memory objects (never all persisted --
# section 6 explicitly warns against that); only the SELECTED decision plus
# a bounded set of top alternatives is durable (see app/models/semantic.py).
# ---------------------------------------------------------------------------


class EvidenceComponentType(StrEnum):
    FIELD_NAME_ALIAS_MATCH = "field_name_alias_match"
    VALUE_PATTERN_MATCH = "value_pattern_match"
    DATATYPE_COMPATIBILITY = "datatype_compatibility"
    DATASET_ROLE_COMPATIBILITY = "dataset_role_compatibility"
    NEIGHBOR_FIELD_CONTEXT = "neighbor_field_context"
    CROSS_DATASET_OVERLAP = "cross_dataset_overlap"
    SEMANTIC_MEMORY = "semantic_memory"
    AI_PROPOSAL = "ai_proposal"
    DETERMINISTIC_COROBORATION = "deterministic_corroboration"


@dataclass(frozen=True)
class InterpretationEvidence:
    component_type: str
    weight: float
    description: str
    supports_concept: str


@dataclass(frozen=True)
class SemanticCandidate:
    source_dataset_id: str
    source_field: str
    candidate_concept: str
    confidence: float
    evidence_components: list[InterpretationEvidence] = field(default_factory=list)
    candidate_rank: int = 0
    generated_by: str = "deterministic_evidence_v1"
    generated_at: datetime = field(default_factory=utc_now)


class InterpretationDecisionStatus(StrEnum):
    AUTO_ACCEPTED = "auto_accepted"
    ACCEPTED_WITH_FLAG = "accepted_with_flag"
    REVIEW_REQUIRED = "review_required"
    UNRESOLVED = "unresolved"
    HUMAN_CONFIRMED = "human_confirmed"
    HUMAN_REJECTED = "human_rejected"


@dataclass(frozen=True)
class InterpretationDecision:
    """Governed field-level interpretation result -- see
    app/models/semantic.py::SemanticInterpretationDecision for the durable
    row this maps onto. Always explainable: "why did Intel4Ops believe
    this field represents this concept" is answerable directly from
    evidence_summary + alternative_candidates."""

    source_dataset_id: str
    source_field: str
    selected_concept: str | None
    confidence: float
    status: str
    evidence_summary: list[str]
    alternative_candidates: list[SemanticCandidate]
    decision_source: str
    decision_version: str
    review_actor_user_id: str | None = None
    review_timestamp: datetime | None = None
