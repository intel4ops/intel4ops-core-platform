from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.entities.entity_type import EntityType
from app.models.entities import utc_now
from app.models.source_system import enum_values, portable_json
from app.process.activity_type import ActivityType, BoundaryStatus, ProcessEdgeType, ProcessStatus

# ---------------------------------------------------------------------------
# P3.xxE.4 Operational Process Interpretation + Canonical Process Graph
# persistence. Production execution surface, reused by AnalysisCase
# orchestration (see tests/test_process_architecture_guardrails.py and
# tests/test_validation_import_boundary.py). Mirrors
# app/models/entities_canonical.py's own conventions exactly: all three
# tables scoped by (organization_id, analysis_case_id, run_id), so no
# query here can ever span more than one run. Minimum-viable persisted
# model set -- 3 tables, not the spec's illustrative 6 (participation,
# state, and multi-hypothesis retention live as JSON/typed columns rather
# than separate tables, justified directly against the real-corpus
# baseline; see the approved plan's "Minimum-viable persisted model set").
# ---------------------------------------------------------------------------


class CanonicalOperationalProcess(Base):
    """One discovered process instance -- either anchored on a real
    CanonicalCaseEntity (anchor_entity_id set) or a single case-level
    anchorless fallback row (anchor_entity_id NULL, process_type
    "UNKNOWN_PROCESS", boundary_status UNKNOWN) when no entity type
    cleared process_anchor_discovery's minimal threshold. process_type,
    process_label, and process_family are three distinct fields (spec
    sections 5/29) -- process_family is a separate, optional, richer
    business classification that never drives structural inference."""

    __tablename__ = "canonical_operational_processes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "analysis_case_id"],
            ["analysis_cases.organization_id", "analysis_cases.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "anchor_entity_id"],
            ["canonical_case_entities.organization_id", "canonical_case_entities.id"],
            ondelete="SET NULL",
        ),
        # Required so CanonicalProcessActivity/CanonicalProcessEdge's
        # composite FKs to (organization_id, id) can target this table --
        # Postgres requires a unique/PK constraint on exactly the
        # referenced column tuple (same pattern as CanonicalCaseEntity's
        # own uq_canonical_case_entities_org_id).
        UniqueConstraint("organization_id", "id", name="uq_canonical_operational_processes_org_id"),
        CheckConstraint(
            f"anchor_entity_type IS NULL OR anchor_entity_type IN ({enum_values(EntityType)})",
            name="ck_canonical_process_anchor_entity_type",
        ),
        CheckConstraint(
            f"boundary_status IN ({enum_values(BoundaryStatus)})",
            name="ck_canonical_process_boundary_status",
        ),
        CheckConstraint(
            f"status IN ({enum_values(ProcessStatus)})",
            name="ck_canonical_process_status",
        ),
        CheckConstraint(
            "anchor_confidence >= 0 AND anchor_confidence <= 1",
            name="ck_canonical_process_anchor_confidence_range",
        ),
        Index(
            "ix_canonical_operational_processes_org_case_run",
            "organization_id",
            "analysis_case_id",
            "run_id",
        ),
        Index("ix_canonical_operational_processes_run_anchor_type", "run_id", "anchor_entity_type"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    analysis_case_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("analysis_case_runs.id", ondelete="CASCADE"), nullable=False
    )
    anchor_entity_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    anchor_entity_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    anchor_confidence: Mapped[float] = mapped_column(default=0.0)
    process_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    process_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    process_family: Mapped[str | None] = mapped_column(String(60), nullable=True)
    process_family_confidence: Mapped[float] = mapped_column(default=0.0)
    boundary_status: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    coverage_confidence: Mapped[float] = mapped_column(default=0.0)
    activity_confidence: Mapped[float] = mapped_column(default=0.0)
    entity_participation_confidence: Mapped[float] = mapped_column(default=0.0)
    temporal_confidence: Mapped[float] = mapped_column(default=0.0)
    precedence_consistency_confidence: Mapped[float] = mapped_column(default=0.0)
    state_transition_confidence: Mapped[float] = mapped_column(default=0.0)
    overall_confidence: Mapped[float] = mapped_column(default=0.0)
    activity_count: Mapped[int] = mapped_column(default=0)
    edge_count: Mapped[int] = mapped_column(default=0)
    evidence_summary: Mapped[list[str]] = mapped_column(portable_json, default=list)
    conflict_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    process_policy_version: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class CanonicalProcessActivity(Base):
    """One discovered activity within one process instance.
    activity_type_confidence/activity_existence_confidence and
    state_existence_confidence/state_meaning_confidence are two DISTINCT
    existence-vs-meaning pairs (plan review correction 1) -- neither side
    of either pair caps the other. corroboration_signals records WHICH
    signal(s) justified this activity's existence (correction 2) -- an
    activity with an empty list here is never persisted at all (see
    app/process/activity_discovery.py)."""

    __tablename__ = "canonical_process_activities"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "process_id"],
            [
                "canonical_operational_processes.organization_id",
                "canonical_operational_processes.id",
            ],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "primary_entity_id"],
            ["canonical_case_entities.organization_id", "canonical_case_entities.id"],
            ondelete="SET NULL",
        ),
        UniqueConstraint("organization_id", "id", name="uq_canonical_process_activities_org_id"),
        CheckConstraint(
            f"activity_type IN ({enum_values(ActivityType)})",
            name="ck_canonical_process_activity_type",
        ),
        CheckConstraint(
            "activity_type_confidence >= 0 AND activity_type_confidence <= 1",
            name="ck_canonical_process_activity_type_confidence_range",
        ),
        CheckConstraint(
            "activity_existence_confidence >= 0 AND activity_existence_confidence <= 1",
            name="ck_canonical_process_activity_existence_confidence_range",
        ),
        CheckConstraint(
            "state_existence_confidence >= 0 AND state_existence_confidence <= 1",
            name="ck_canonical_process_activity_state_existence_confidence_range",
        ),
        CheckConstraint(
            "state_meaning_confidence >= 0 AND state_meaning_confidence <= 1",
            name="ck_canonical_process_activity_state_meaning_confidence_range",
        ),
        Index("ix_canonical_process_activities_process", "process_id"),
        Index("ix_canonical_process_activities_primary_entity", "primary_entity_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    process_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    activity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    activity_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    state_value: Mapped[str | None] = mapped_column(String(100), nullable=True)
    primary_entity_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    activity_type_confidence: Mapped[float] = mapped_column(default=0.0)
    activity_existence_confidence: Mapped[float] = mapped_column(default=0.0)
    temporal_confidence: Mapped[float] = mapped_column(default=0.0)
    participation_confidence: Mapped[float] = mapped_column(default=0.0)
    activity_confidence: Mapped[float] = mapped_column(default=0.0)
    state_existence_confidence: Mapped[float] = mapped_column(default=0.0)
    state_meaning_confidence: Mapped[float] = mapped_column(default=0.0)
    temporal_evidence_tier: Mapped[str] = mapped_column(String(10), nullable=False)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    occurred_at_precision: Mapped[str] = mapped_column(String(20), nullable=False)
    timezone_source: Mapped[str] = mapped_column(String(20), nullable=False)
    is_explicit_event: Mapped[bool] = mapped_column(default=False)
    corroboration_signals: Mapped[list[str]] = mapped_column(portable_json, default=list)
    alternative_activity_types: Mapped[list[dict[str, object]]] = mapped_column(
        portable_json, default=list
    )
    participation: Mapped[list[dict[str, object]]] = mapped_column(portable_json, default=list)
    source_refs: Mapped[list[dict[str, object]]] = mapped_column(portable_json, default=list)
    evidence_summary: Mapped[list[str]] = mapped_column(portable_json, default=list)
    activity_policy_version: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class CanonicalProcessEdge(Base):
    """One discovered directed (or explicitly non-directed, e.g.
    CONCURRENT/ORDER_UNRESOLVED) relationship between two
    CanonicalProcessActivity rows in the same process instance. State
    transitions fold into this table (edge_type STATE_TRANSITION +
    from_state/to_state) rather than a separate table -- structurally a
    directed edge with two extra nullable columns. Every confidence
    component persisted separately, never collapsed to one opaque number
    (spec section 17) -- see app/process/precedence_confidence.py."""

    __tablename__ = "canonical_process_edges"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "process_id"],
            [
                "canonical_operational_processes.organization_id",
                "canonical_operational_processes.id",
            ],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "from_activity_id"],
            ["canonical_process_activities.organization_id", "canonical_process_activities.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "to_activity_id"],
            ["canonical_process_activities.organization_id", "canonical_process_activities.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "from_activity_id != to_activity_id", name="ck_canonical_process_edge_no_self"
        ),
        CheckConstraint(
            f"edge_type IN ({enum_values(ProcessEdgeType)})",
            name="ck_canonical_process_edge_type",
        ),
        CheckConstraint(
            f"status IN ({enum_values(ProcessStatus)})",
            name="ck_canonical_process_edge_status",
        ),
        CheckConstraint(
            "precedence_confidence >= 0 AND precedence_confidence <= 1",
            name="ck_canonical_process_edge_precedence_confidence_range",
        ),
        Index("ix_canonical_process_edges_process", "process_id"),
        Index("ix_canonical_process_edges_from_to", "from_activity_id", "to_activity_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    process_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    from_activity_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    to_activity_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    edge_type: Mapped[str] = mapped_column(String(20), nullable=False)
    from_state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    to_state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    support_count: Mapped[int] = mapped_column(default=0)
    a_before_b_count: Mapped[int] = mapped_column(default=0)
    b_before_a_count: Mapped[int] = mapped_column(default=0)
    same_time_count: Mapped[int] = mapped_column(default=0)
    unknown_order_count: Mapped[int] = mapped_column(default=0)
    observation_count: Mapped[int] = mapped_column(default=0)
    temporal_evidence_tier: Mapped[str] = mapped_column(String(10), nullable=False)
    semantic_confidence: Mapped[float] = mapped_column(default=0.0)
    entity_participation_confidence: Mapped[float] = mapped_column(default=0.0)
    temporal_confidence: Mapped[float] = mapped_column(default=0.0)
    repetition_confidence: Mapped[float] = mapped_column(default=0.0)
    consistency_confidence: Mapped[float] = mapped_column(default=0.0)
    conflict_penalty: Mapped[float] = mapped_column(default=0.0)
    precedence_confidence: Mapped[float] = mapped_column(default=0.0)
    contradiction_count: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    evidence_summary: Mapped[list[str]] = mapped_column(portable_json, default=list)
    conflict_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    edge_policy_version: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
