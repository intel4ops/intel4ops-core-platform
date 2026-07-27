from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.knowledge_graph.catalog import EVIDENCE_SOURCE_TYPES, SOURCE_REGISTRIES
from app.models.entities import portable_json, utc_now

GOVERNANCE_LIFECYCLE = (
    "draft",
    "under_review",
    "approved",
    "active",
    "suspended",
    "deprecated",
    "retired",
)


class KnowledgeGraphEntityType(Base):
    __tablename__ = "knowledge_graph_entity_types"
    __table_args__ = (
        CheckConstraint(
            "lifecycle_status IN "
            "('draft','under_review','approved','active','suspended','deprecated','retired')",
            name="ck_kg_entity_type_lifecycle",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(160), unique=True)
    name: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text)
    lifecycle_status: Mapped[str] = mapped_column(String(30), default="draft")
    owner: Mapped[str] = mapped_column(String(120))
    security_classification: Mapped[str] = mapped_column(String(40), default="internal")
    tags: Mapped[list[str]] = mapped_column(portable_json, default=list)
    documentation_reference: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class KnowledgeGraphEntityTypeVersion(Base):
    __tablename__ = "knowledge_graph_entity_type_versions"
    __table_args__ = (
        UniqueConstraint("entity_type_id", "semantic_version", name="uq_kg_entity_type_version"),
        UniqueConstraint("definition_hash", name="uq_kg_entity_type_definition_hash"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    entity_type_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_graph_entity_types.id", ondelete="RESTRICT")
    )
    semantic_version: Mapped[str] = mapped_column(String(30))
    source_registries: Mapped[list[str]] = mapped_column(portable_json)
    reference_contract: Mapped[dict[str, object]] = mapped_column(portable_json)
    property_contract: Mapped[dict[str, object]] = mapped_column(portable_json)
    validation_contract: Mapped[dict[str, object]] = mapped_column(portable_json)
    retention_policy: Mapped[dict[str, object]] = mapped_column(portable_json)
    known_limitations: Mapped[list[str]] = mapped_column(portable_json, default=list)
    definition_hash: Mapped[str] = mapped_column(String(64))
    approved_by_user_id: Mapped[UUID | None] = mapped_column(Uuid)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class KnowledgeGraphRelationshipType(Base):
    __tablename__ = "knowledge_graph_relationship_types"
    __table_args__ = (
        CheckConstraint(
            "lifecycle_status IN "
            "('draft','under_review','approved','active','suspended','deprecated','retired')",
            name="ck_kg_relationship_type_lifecycle",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(160), unique=True)
    name: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text)
    lifecycle_status: Mapped[str] = mapped_column(String(30), default="draft")
    directed: Mapped[bool] = mapped_column(Boolean, default=True)
    symmetric: Mapped[bool] = mapped_column(Boolean, default=False)
    owner: Mapped[str] = mapped_column(String(120))
    security_classification: Mapped[str] = mapped_column(String(40), default="internal")
    documentation_reference: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class KnowledgeGraphRelationshipTypeVersion(Base):
    __tablename__ = "knowledge_graph_relationship_type_versions"
    __table_args__ = (
        UniqueConstraint(
            "relationship_type_id",
            "semantic_version",
            name="uq_kg_relationship_type_version",
        ),
        UniqueConstraint("definition_hash", name="uq_kg_relationship_definition_hash"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    relationship_type_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_graph_relationship_types.id", ondelete="RESTRICT")
    )
    semantic_version: Mapped[str] = mapped_column(String(30))
    allowed_from_entity_codes: Mapped[list[str]] = mapped_column(portable_json)
    allowed_to_entity_codes: Mapped[list[str]] = mapped_column(portable_json)
    inverse_relationship_code: Mapped[str | None] = mapped_column(String(160))
    evidence_contract: Mapped[dict[str, object]] = mapped_column(portable_json)
    confidence_policy: Mapped[dict[str, object]] = mapped_column(portable_json)
    temporal_policy: Mapped[dict[str, object]] = mapped_column(portable_json)
    revalidation_policy: Mapped[dict[str, object]] = mapped_column(portable_json)
    known_limitations: Mapped[list[str]] = mapped_column(portable_json, default=list)
    definition_hash: Mapped[str] = mapped_column(String(64))
    approved_by_user_id: Mapped[UUID | None] = mapped_column(Uuid)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class KnowledgeGraphGovernanceEvent(Base):
    __tablename__ = "knowledge_graph_governance_events"
    __table_args__ = (
        UniqueConstraint("asset_type", "asset_id", "idempotency_key", name="uq_kg_governance_key"),
        Index("ix_kg_governance_asset_time", "asset_type", "asset_id", "occurred_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    asset_type: Mapped[str] = mapped_column(String(40))
    asset_id: Mapped[UUID] = mapped_column(Uuid)
    prior_status: Mapped[str | None] = mapped_column(String(30))
    new_status: Mapped[str] = mapped_column(String(30))
    actor_user_id: Mapped[UUID] = mapped_column(Uuid)
    actor_role: Mapped[str] = mapped_column(String(50))
    reason: Mapped[str] = mapped_column(Text)
    approval_reference: Mapped[str | None] = mapped_column(String(255))
    idempotency_key: Mapped[str] = mapped_column(String(255))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class KnowledgeGraphVersion(Base):
    __tablename__ = "knowledge_graph_versions"
    __table_args__ = (
        UniqueConstraint("organization_id", "version", name="uq_kg_version_org_number"),
        UniqueConstraint("organization_id", "id", name="uq_kg_version_org_id"),
        CheckConstraint(
            "status IN ('building','validating','active','superseded','failed','retired')",
            name="ck_kg_version_status",
        ),
        Index("ix_kg_version_org_status", "organization_id", "status"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="building")
    source_cutoff_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    definition_fingerprint: Mapped[str] = mapped_column(String(64))
    node_count: Mapped[int] = mapped_column(Integer, default=0)
    edge_count: Mapped[int] = mapped_column(Integer, default=0)
    validation_summary: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class KnowledgeGraphNode(Base):
    __tablename__ = "knowledge_graph_nodes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "graph_version_id"],
            ["knowledge_graph_versions.organization_id", "knowledge_graph_versions.id"],
            name="fk_kg_node_org_graph_version",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "organization_id",
            "graph_version_id",
            "id",
            name="uq_kg_node_org_graph_id",
        ),
        UniqueConstraint(
            "organization_id",
            "graph_version_id",
            "entity_type_version_id",
            "source_registry",
            "source_object_id",
            "source_version_key",
            name="uq_kg_node_reference",
        ),
        CheckConstraint(
            "status IN ('active','superseded','unavailable','retired')",
            name="ck_kg_node_status",
        ),
        CheckConstraint(
            "source_registry IN ("
            + ",".join(f"'{registry}'" for registry in sorted(SOURCE_REGISTRIES))
            + ")",
            name="ck_kg_node_source_registry",
        ),
        Index(
            "ix_kg_node_org_graph_type",
            "organization_id",
            "graph_version_id",
            "entity_type_version_id",
        ),
        Index(
            "ix_kg_node_org_source",
            "organization_id",
            "source_registry",
            "source_object_id",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid)
    graph_version_id: Mapped[UUID] = mapped_column(Uuid)
    entity_type_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_graph_entity_type_versions.id", ondelete="RESTRICT")
    )
    source_registry: Mapped[str] = mapped_column(String(80))
    source_object_id: Mapped[UUID] = mapped_column(Uuid)
    source_version_id: Mapped[UUID | None] = mapped_column(Uuid)
    source_version_key: Mapped[str] = mapped_column(String(64), default="")
    stable_code: Mapped[str | None] = mapped_column(String(180))
    display_label: Mapped[str | None] = mapped_column(String(255))
    reference_fingerprint: Mapped[str] = mapped_column(String(64))
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), default="active")
    metadata_json: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class KnowledgeGraphEdge(Base):
    __tablename__ = "knowledge_graph_edges"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "graph_version_id", "from_node_id"],
            [
                "knowledge_graph_nodes.organization_id",
                "knowledge_graph_nodes.graph_version_id",
                "knowledge_graph_nodes.id",
            ],
            name="fk_kg_edge_from_node_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "graph_version_id", "to_node_id"],
            [
                "knowledge_graph_nodes.organization_id",
                "knowledge_graph_nodes.graph_version_id",
                "knowledge_graph_nodes.id",
            ],
            name="fk_kg_edge_to_node_tenant",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "organization_id",
            "graph_version_id",
            "from_node_id",
            "to_node_id",
            "relationship_type_version_id",
            "derivation_fingerprint",
            "validity_key",
            name="uq_kg_edge_identity",
        ),
        UniqueConstraint(
            "organization_id",
            "graph_version_id",
            "id",
            name="uq_kg_edge_org_graph_id",
        ),
        CheckConstraint("from_node_id != to_node_id", name="ck_kg_edge_not_self"),
        CheckConstraint(
            "assertion_kind IN ('observed','declared','calculated','inferred','reviewed')",
            name="ck_kg_edge_assertion_kind",
        ),
        CheckConstraint(
            "status IN ('proposed','active','disputed','superseded','expired','retired')",
            name="ck_kg_edge_status",
        ),
        CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 1",
            name="ck_kg_edge_confidence",
        ),
        Index(
            "ix_kg_edge_org_graph_from_type",
            "organization_id",
            "graph_version_id",
            "from_node_id",
            "relationship_type_version_id",
            "status",
        ),
        Index(
            "ix_kg_edge_org_graph_to_type",
            "organization_id",
            "graph_version_id",
            "to_node_id",
            "relationship_type_version_id",
            "status",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid)
    graph_version_id: Mapped[UUID] = mapped_column(Uuid)
    relationship_type_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_graph_relationship_type_versions.id", ondelete="RESTRICT")
    )
    from_node_id: Mapped[UUID] = mapped_column(Uuid)
    to_node_id: Mapped[UUID] = mapped_column(Uuid)
    assertion_kind: Mapped[str] = mapped_column(String(30))
    derivation_method: Mapped[str] = mapped_column(String(180))
    derivation_version: Mapped[str] = mapped_column(String(30))
    derivation_fingerprint: Mapped[str] = mapped_column(String(64))
    confidence_score: Mapped[Decimal] = mapped_column(Numeric(8, 7))
    confidence_method: Mapped[str] = mapped_column(String(120))
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    validity_key: Mapped[str] = mapped_column(String(64), default="")
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), default="active")
    definition_fingerprint: Mapped[str] = mapped_column(String(64))
    content_fingerprint: Mapped[str] = mapped_column(String(64))
    properties_json: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class KnowledgeGraphEdgeEvidence(Base):
    __tablename__ = "knowledge_graph_edge_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "graph_version_id", "edge_id"],
            [
                "knowledge_graph_edges.organization_id",
                "knowledge_graph_edges.graph_version_id",
                "knowledge_graph_edges.id",
            ],
            name="fk_kg_edge_evidence_tenant",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "edge_id",
            "source_type",
            "source_identifier",
            "integrity_fingerprint",
            name="uq_kg_edge_evidence_reference",
        ),
        CheckConstraint(
            "source_type IN ("
            + ",".join(f"'{source_type}'" for source_type in sorted(EVIDENCE_SOURCE_TYPES))
            + ")",
            name="ck_kg_edge_evidence_source_type",
        ),
        Index("ix_kg_edge_evidence_org_edge", "organization_id", "edge_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid)
    graph_version_id: Mapped[UUID] = mapped_column(Uuid)
    edge_id: Mapped[UUID] = mapped_column(Uuid)
    source_type: Mapped[str] = mapped_column(String(80))
    source_identifier: Mapped[str] = mapped_column(String(500))
    source_object_id: Mapped[UUID | None] = mapped_column(Uuid)
    lineage_node_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("lineage_nodes.id", ondelete="SET NULL")
    )
    integrity_fingerprint: Mapped[str] = mapped_column(String(128))
    relevance: Mapped[str] = mapped_column(String(40), default="supporting")
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class KnowledgeGraphChange(Base):
    __tablename__ = "knowledge_graph_changes"
    __table_args__ = (
        UniqueConstraint("organization_id", "idempotency_key", name="uq_kg_change_key"),
        UniqueConstraint(
            "organization_id",
            "adapter_code",
            "source_event_id",
            name="uq_kg_change_source_event",
        ),
        Index("ix_kg_change_org_time", "organization_id", "occurred_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    graph_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_graph_versions.id", ondelete="CASCADE")
    )
    adapter_code: Mapped[str] = mapped_column(String(120))
    adapter_version: Mapped[str] = mapped_column(String(30))
    source_event_id: Mapped[str] = mapped_column(String(255))
    source_fingerprint: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(30))
    node_count: Mapped[int] = mapped_column(Integer, default=0)
    edge_count: Mapped[int] = mapped_column(Integer, default=0)
    result_json: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class KnowledgeGraphQueryRun(Base):
    __tablename__ = "knowledge_graph_query_runs"
    __table_args__ = (
        UniqueConstraint("organization_id", "idempotency_key", name="uq_kg_query_key"),
        Index("ix_kg_query_org_time", "organization_id", "started_at"),
        CheckConstraint(
            "operation IN "
            "('neighborhood','shortest_governed_path','upstream_evidence','downstream_impact',"
            "'intervention_to_outcome','value_trace')",
            name="ck_kg_query_operation",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    graph_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_graph_versions.id", ondelete="RESTRICT")
    )
    idempotency_key: Mapped[str] = mapped_column(String(255))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    operation: Mapped[str] = mapped_column(String(50))
    request_json: Mapped[dict[str, object]] = mapped_column(portable_json)
    status: Mapped[str] = mapped_column(String(30))
    max_depth: Mapped[int] = mapped_column(Integer)
    max_nodes: Mapped[int] = mapped_column(Integer)
    max_edges: Mapped[int] = mapped_column(Integer)
    max_paths: Mapped[int] = mapped_column(Integer)
    timeout_ms: Mapped[int] = mapped_column(Integer)
    returned_nodes: Mapped[int] = mapped_column(Integer, default=0)
    returned_edges: Mapped[int] = mapped_column(Integer, default=0)
    returned_paths: Mapped[int] = mapped_column(Integer, default=0)
    truncated: Mapped[bool] = mapped_column(Boolean, default=False)
    result_summary: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    requested_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retain_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class KnowledgeGraphQueryStep(Base):
    __tablename__ = "knowledge_graph_query_steps"
    __table_args__ = (
        UniqueConstraint("query_run_id", "sequence", name="uq_kg_query_step_sequence"),
        Index("ix_kg_query_step_org_run", "organization_id", "query_run_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    query_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_graph_query_runs.id", ondelete="CASCADE")
    )
    sequence: Mapped[int] = mapped_column(Integer)
    depth: Mapped[int] = mapped_column(Integer)
    from_node_id: Mapped[UUID | None] = mapped_column(Uuid)
    edge_id: Mapped[UUID | None] = mapped_column(Uuid)
    to_node_id: Mapped[UUID] = mapped_column(Uuid)
    explanation_json: Mapped[dict[str, object]] = mapped_column(portable_json)
    evidence_references: Mapped[list[object]] = mapped_column(portable_json, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class KnowledgeGraphProjectionCheckpoint(Base):
    __tablename__ = "knowledge_graph_projection_checkpoints"
    __table_args__ = (
        UniqueConstraint("organization_id", "adapter_code", name="uq_kg_checkpoint_adapter"),
        Index("ix_kg_checkpoint_org_time", "organization_id", "updated_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    adapter_code: Mapped[str] = mapped_column(String(120))
    adapter_version: Mapped[str] = mapped_column(String(30))
    source_cursor: Mapped[str] = mapped_column(String(500))
    source_fingerprint: Mapped[str] = mapped_column(String(64))
    graph_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_graph_versions.id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(String(30))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


def _immutable(*_: object) -> None:
    raise ValueError("published knowledge graph history is immutable")


for immutable_model in (
    KnowledgeGraphEntityTypeVersion,
    KnowledgeGraphRelationshipTypeVersion,
    KnowledgeGraphGovernanceEvent,
    KnowledgeGraphEdgeEvidence,
    KnowledgeGraphChange,
    KnowledgeGraphQueryStep,
):
    event.listen(immutable_model, "before_update", _immutable)
    event.listen(immutable_model, "before_delete", _immutable)
