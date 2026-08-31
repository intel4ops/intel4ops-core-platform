from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

# ---------------------------------------------------------------------------
# P3.xxE.4 sections 6/7/13/14: ephemeral activity/participation/edge
# candidate objects. Mirrors app/entities/entity_candidate.py's convention
# exactly -- cheap, in-memory dataclasses; only the resolved
# CanonicalProcessActivity/CanonicalProcessEdge + a bounded evidence
# summary are durable.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ActivityObservation:
    """One field's contribution toward a candidate activity. Framework-free
    (no UUID import), matching app/entities/entity_candidate.py's own
    convention. semantic_status is the RAW machine status (auto_accepted/
    accepted_with_flag/review_required/unresolved) -- the full 5-tier
    hierarchy from plan review correction 1, not a pre-collapsed bool."""

    analysis_case_dataset_id: str
    dataset_label: str
    dataset_role: str
    source_field: str
    concept_code: str
    semantic_status: str
    semantic_confidence: float
    primary_entity_id: str | None
    primary_entity_type: str | None
    occurred_at: datetime | None
    occurred_at_precision: str
    timezone_source: str
    raw_state_value: str | None
    corroboration_signals: list[str] = field(default_factory=list)
    is_explicit_event: bool = False


@dataclass(frozen=True)
class ParticipationCandidate:
    entity_id: str
    entity_type: str
    role: str
    role_confidence: float
    evidence: str


@dataclass(frozen=True)
class ActivityCandidate:
    """One candidate operational activity. activity_type_confidence and
    activity_existence_confidence stay independent (plan review
    correction 1's existence-vs-meaning split, mirroring E.3's
    entity_type_confidence/entity_identity_confidence split); the same
    split is repeated for state_existence_confidence/state_meaning_confidence."""

    activity_type: str
    activity_label: str | None
    state_value: str | None
    primary_entity_id: str | None
    primary_entity_type: str | None
    observations: list[ActivityObservation] = field(default_factory=list)
    activity_type_confidence: float = 0.0
    activity_existence_confidence: float = 0.0
    temporal_confidence: float = 0.0
    participation_confidence: float = 0.0
    activity_confidence: float = 0.0
    state_existence_confidence: float = 0.0
    state_meaning_confidence: float = 0.0
    temporal_evidence_tier: str = "NONE"
    occurred_at: datetime | None = None
    occurred_at_precision: str = "unknown"
    timezone_source: str = "unspecified"
    is_explicit_event: bool = False
    corroboration_signals: list[str] = field(default_factory=list)
    alternative_activity_types: list[dict[str, object]] = field(default_factory=list)
    participation: list[ParticipationCandidate] = field(default_factory=list)
    evidence_summary: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ProcessEdgeCandidate:
    """References activities by their POSITION in the owning process
    instance's ActivityCandidate list (left_index/right_index) --
    activities have no stable business key before DB insert, unlike
    entities' normalized_key; the orchestration layer resolves indices to
    real CanonicalProcessActivity.id values at persistence time."""

    left_index: int
    right_index: int
    edge_type: str
    from_state: str | None
    to_state: str | None
    support_count: int
    a_before_b_count: int
    b_before_a_count: int
    same_time_count: int
    unknown_order_count: int
    observation_count: int
    temporal_evidence_tier: str
    semantic_confidence: float
    entity_participation_confidence: float
    temporal_confidence: float
    repetition_confidence: float
    consistency_confidence: float
    conflict_penalty: float
    precedence_confidence: float
    contradiction_count: int
    status: str
    evidence_summary: list[str] = field(default_factory=list)
    conflict_reason: str | None = None
