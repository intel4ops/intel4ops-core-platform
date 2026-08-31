from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProcessRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    analysis_case_id: UUID
    run_id: UUID
    anchor_entity_id: UUID | None
    anchor_entity_type: str | None
    anchor_confidence: float
    process_type: str | None
    process_label: str | None
    process_family: str | None
    process_family_confidence: float
    boundary_status: str
    status: str
    coverage_confidence: float
    activity_confidence: float
    entity_participation_confidence: float
    temporal_confidence: float
    precedence_consistency_confidence: float
    state_transition_confidence: float
    overall_confidence: float
    activity_count: int
    edge_count: int
    evidence_summary: list[str]
    conflict_reason: str | None
    process_policy_version: str
    created_at: datetime


class ActivityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    process_id: UUID
    activity_type: str
    activity_label: str | None
    state_value: str | None
    primary_entity_id: UUID | None
    activity_type_confidence: float
    activity_existence_confidence: float
    temporal_confidence: float
    participation_confidence: float
    activity_confidence: float
    state_existence_confidence: float
    state_meaning_confidence: float
    temporal_evidence_tier: str
    occurred_at: datetime | None
    occurred_at_precision: str
    timezone_source: str
    is_explicit_event: bool
    corroboration_signals: list[str]
    alternative_activity_types: list[dict[str, object]]
    participation: list[dict[str, object]]
    source_refs: list[dict[str, object]]
    evidence_summary: list[str]
    activity_policy_version: str
    created_at: datetime


class EdgeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    process_id: UUID
    from_activity_id: UUID
    to_activity_id: UUID
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
    evidence_summary: list[str]
    conflict_reason: str | None
    edge_policy_version: str
    created_at: datetime


class ProcessListRead(BaseModel):
    analysis_case_id: UUID
    run_id: UUID | None
    processes: list[ProcessRead] = Field(default_factory=list)


class ProcessDetailRead(ProcessRead):
    activities: list[ActivityRead] = Field(default_factory=list)
    edges: list[EdgeRead] = Field(default_factory=list)


class ActivityListRead(BaseModel):
    analysis_case_id: UUID
    process_id: UUID
    activities: list[ActivityRead] = Field(default_factory=list)


class EdgeListRead(BaseModel):
    analysis_case_id: UUID
    process_id: UUID
    edges: list[EdgeRead] = Field(default_factory=list)


class ProcessGraphNodeRead(BaseModel):
    id: UUID
    process_id: UUID
    activity_type: str
    state_value: str | None
    occurred_at: datetime | None
    activity_confidence: float


class ProcessGraphEdgeRead(BaseModel):
    id: UUID
    from_activity_id: UUID
    to_activity_id: UUID
    edge_type: str
    status: str
    precedence_confidence: float


class ProcessGraphRead(BaseModel):
    """Relational read composition, NOT a graph-DB-backed model -- purely
    a join of CanonicalOperationalProcess/CanonicalProcessActivity/
    CanonicalProcessEdge for one run, shaped for a graph viewer. Mirrors
    app/schemas/entities.py::EntityGraphRead's own precedent exactly."""

    analysis_case_id: UUID
    run_id: UUID | None
    nodes: list[ProcessGraphNodeRead] = Field(default_factory=list)
    edges: list[ProcessGraphEdgeRead] = Field(default_factory=list)


class ProcessGraphSummaryRead(BaseModel):
    analysis_case_id: UUID
    run_id: UUID | None
    process_count: int
    activity_count: int
    edge_count: int
    boundary_status_counts: dict[str, int] = Field(default_factory=dict)
    status_counts: dict[str, int] = Field(default_factory=dict)
    activity_type_counts: dict[str, int] = Field(default_factory=dict)
