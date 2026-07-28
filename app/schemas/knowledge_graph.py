from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GraphEntityTypeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    code: str
    name: str
    description: str
    lifecycle_status: str


class GraphRelationshipTypeRead(GraphEntityTypeRead):
    directed: bool
    symmetric: bool


class GraphEntityTypeVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    entity_type_id: UUID
    semantic_version: str
    source_registries: list[str]
    reference_contract: dict[str, object]
    definition_hash: str


class GraphRelationshipTypeVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    relationship_type_id: UUID
    semantic_version: str
    allowed_from_entity_codes: list[str]
    allowed_to_entity_codes: list[str]
    evidence_contract: dict[str, object]
    definition_hash: str


class GraphTypeTransition(BaseModel):
    asset_type: Literal["entity_type", "relationship_type"]
    target_status: Literal[
        "draft",
        "under_review",
        "approved",
        "active",
        "suspended",
        "deprecated",
        "retired",
    ]
    reason: str = Field(min_length=1, max_length=2000)
    idempotency_key: str = Field(min_length=1, max_length=255)


class GraphVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    version: int
    status: str
    node_count: int
    edge_count: int
    created_at: datetime
    published_at: datetime | None


class GraphNodeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    graph_version_id: UUID
    source_registry: str
    source_object_id: UUID
    stable_code: str | None
    display_label: str | None
    status: str


class GraphEdgeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    from_node_id: UUID
    to_node_id: UUID
    confidence_score: float
    status: str


class FindingProjectionCreate(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=255)
    finding_id: UUID
    source_event_id: str = Field(min_length=1, max_length=255)


class ProjectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    graph_version_id: UUID
    adapter_code: str
    source_event_id: str
    status: str
    node_count: int
    edge_count: int


class GraphTraversalCreate(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=255)
    start_node_id: UUID
    target_node_id: UUID | None = None
    graph_version_id: UUID | None = None
    operation: Literal[
        "neighborhood",
        "shortest_governed_path",
        "upstream_evidence",
        "downstream_impact",
        "intervention_to_outcome",
        "value_trace",
    ] = "neighborhood"
    direction: Literal["outbound", "inbound", "both"] = "both"
    relationship_codes: list[str] = Field(default_factory=list, max_length=26)
    max_depth: int = Field(default=3, ge=1, le=6)
    max_nodes: int = Field(default=100, ge=1, le=1000)
    max_edges: int = Field(default=250, ge=1, le=2500)
    max_paths: int = Field(default=25, ge=1, le=100)
    timeout_ms: int = Field(default=2000, ge=1, le=5000)
    minimum_confidence: float = Field(default=0, ge=0, le=1)
    point_in_time: datetime | None = None

    @model_validator(mode="after")
    def validate_operation_contract(self) -> GraphTraversalCreate:
        if self.operation == "shortest_governed_path" and self.target_node_id is None:
            raise ValueError("target_node_id is required for shortest_governed_path")
        return self


class GraphTraversalRead(BaseModel):
    run_id: UUID
    graph_version_id: UUID
    nodes: list[GraphNodeRead]
    edges: list[GraphEdgeRead]
    paths: list[list[UUID]]
    truncated: bool
    warnings: list[str]


class GraphExplanationRead(BaseModel):
    run_id: UUID
    graph_version_id: UUID
    steps: list[dict[str, object]]
    limitations: list[str]


class GraphHealthRead(BaseModel):
    graph_version_id: UUID | None
    status: str
    node_count: int
    edge_count: int
    orphan_count: int
