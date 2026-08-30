from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EntityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    analysis_case_id: UUID
    run_id: UUID
    entity_type: str
    canonical_key: str
    display_label: str
    entity_type_confidence: float
    entity_identity_confidence: float
    resolution_method: str
    evidence_summary: list[str]
    resolution_policy_version: str
    created_at: datetime


class EntityObservationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    canonical_entity_id: UUID
    analysis_case_dataset_id: UUID
    source_field: str
    concept_code: str
    raw_value: str | None
    raw_value_hash: str | None
    normalized_value: str
    semantic_confidence: float
    semantic_source: str
    human_validated: bool
    created_at: datetime


class EntityDetailRead(EntityRead):
    observations: list[EntityObservationRead] = Field(default_factory=list)


class RelationshipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    analysis_case_id: UUID
    run_id: UUID
    left_entity_id: UUID
    right_entity_id: UUID
    relationship_type: str
    cardinality: str
    left_entity_identity_confidence: float
    right_entity_identity_confidence: float
    structural_evidence_confidence: float
    relationship_confidence: float
    status: str
    evidence_summary: list[str]
    conflict_reason: str | None
    relationship_policy_version: str
    created_at: datetime


class EntityListRead(BaseModel):
    analysis_case_id: UUID
    run_id: UUID | None
    entities: list[EntityRead] = Field(default_factory=list)


class RelationshipListRead(BaseModel):
    analysis_case_id: UUID
    run_id: UUID | None
    relationships: list[RelationshipRead] = Field(default_factory=list)


class EntityGraphNodeRead(BaseModel):
    id: UUID
    entity_type: str
    canonical_key: str
    display_label: str
    entity_identity_confidence: float


class EntityGraphEdgeRead(BaseModel):
    id: UUID
    left_entity_id: UUID
    right_entity_id: UUID
    relationship_type: str
    cardinality: str
    status: str
    relationship_confidence: float


class EntityGraphRead(BaseModel):
    """Relational read composition, NOT a graph-DB-backed model -- purely
    a join of CanonicalCaseEntity + CanonicalCaseRelationship for one run, shaped
    for a graph viewer. Reflects only the P3.xxE.3 canonical layer, never
    blended with the legacy AnalysisCaseEntityLink system (plan review
    correction 3)."""

    analysis_case_id: UUID
    run_id: UUID | None
    nodes: list[EntityGraphNodeRead] = Field(default_factory=list)
    edges: list[EntityGraphEdgeRead] = Field(default_factory=list)
