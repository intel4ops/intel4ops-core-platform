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
from app.entities.relationship_type import Cardinality, RelationshipStatus, RelationshipType
from app.models.entities import utc_now
from app.models.source_system import enum_values, portable_json

# ---------------------------------------------------------------------------
# P3.xxE.3 Entity + Relationship Intelligence persistence. Production
# execution surface, reused by AnalysisCase orchestration (see
# tests/test_entities_architecture_guardrails.py and
# tests/test_validation_import_boundary.py). All three tables are scoped
# by (organization_id, analysis_case_id, run_id) -- deliberately, this is
# the structural fix for what got Canonical Mapping's cross-run, org-wide
# EntityResolutionService/CanonicalCaseEntity rejected as a reuse target (see
# the P3.xxE.3 plan's reconciliation table): no query here can ever span
# more than one run, by construction, so there is no cross-run entity
# memory to accidentally introduce.
#
# Recomputed fresh on every run (same latest-state convention as
# SemanticInterpretationDecision), never deleted-and-recreated like the
# legacy AnalysisCaseEntityLink -- a new run's rows simply carry a new
# run_id, preserving run-history comparability. Not append-only/immutable
# like SemanticReview/SemanticDecisionVersion -- there is no human-edit
# history to protect here.
# ---------------------------------------------------------------------------


class CanonicalCaseEntity(Base):
    """One resolved entity within one run. entity_type_confidence and
    entity_identity_confidence are DISTINCT columns (plan review
    correction 1) -- neither caps the other. See
    app/entities/entity_deduplication.py for how they're computed."""

    __tablename__ = "canonical_case_entities"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "analysis_case_id"],
            ["analysis_cases.organization_id", "analysis_cases.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "run_id",
            "entity_type",
            "canonical_key",
            name="uq_canonical_case_entity_run_type_key",
        ),
        # Required so CanonicalCaseRelationship's composite FKs to
        # (organization_id, id) can target this table -- Postgres requires
        # a unique/PK constraint on exactly the referenced column tuple,
        # not just a PK on id alone (same pattern as AnalysisCase's own
        # UniqueConstraint("organization_id", "id")).
        UniqueConstraint("organization_id", "id", name="uq_canonical_case_entities_org_id"),
        CheckConstraint(
            f"entity_type IN ({enum_values(EntityType)})",
            name="ck_canonical_case_entity_type",
        ),
        CheckConstraint(
            "entity_type_confidence >= 0 AND entity_type_confidence <= 1",
            name="ck_canonical_case_entity_type_confidence_range",
        ),
        CheckConstraint(
            "entity_identity_confidence >= 0 AND entity_identity_confidence <= 1",
            name="ck_canonical_case_entity_identity_confidence_range",
        ),
        Index(
            "ix_canonical_case_entities_org_case_run",
            "organization_id",
            "analysis_case_id",
            "run_id",
        ),
        Index("ix_canonical_case_entities_run_type", "run_id", "entity_type"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    analysis_case_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("analysis_case_runs.id", ondelete="CASCADE"), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    canonical_key: Mapped[str] = mapped_column(String(300), nullable=False)
    display_label: Mapped[str] = mapped_column(String(300), nullable=False)
    entity_type_confidence: Mapped[float] = mapped_column(default=0.0)
    entity_identity_confidence: Mapped[float] = mapped_column(default=0.0)
    resolution_method: Mapped[str] = mapped_column(String(20), nullable=False)
    evidence_summary: Mapped[list[str]] = mapped_column(portable_json, default=list)
    resolution_policy_version: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class CanonicalEntityObservation(Base):
    """Persisted source lineage for one CanonicalCaseEntity (Invariant E: every
    canonical entity retains its source observations) -- NOT ephemeral,
    unlike app/entities/entity_candidate.py's EntityObservation dataclass
    it's built from.

    Privacy-corrected persistence policy (plan review): raw_value is
    stored verbatim only for non-sensitive entity types (business codes
    like asset_id/work_order_id); for PERSON/CUSTOMER, raw_value stays
    NULL and raw_value_hash (sha256) is stored instead -- see
    app/entities/entity_type.py::observation_value_fields."""

    __tablename__ = "canonical_case_entity_observations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "canonical_entity_id"],
            ["canonical_case_entities.organization_id", "canonical_case_entities.id"],
            ondelete="CASCADE",
        ),
        Index("ix_canonical_case_entity_observations_entity", "canonical_entity_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    canonical_entity_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    analysis_case_dataset_id: Mapped[UUID] = mapped_column(
        ForeignKey("analysis_case_datasets.id", ondelete="CASCADE"), nullable=False
    )
    source_field: Mapped[str] = mapped_column(String(255), nullable=False)
    concept_code: Mapped[str] = mapped_column(String(100), nullable=False)
    raw_value: Mapped[str | None] = mapped_column(String(500), nullable=True)
    raw_value_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    normalized_value: Mapped[str] = mapped_column(String(500), nullable=False)
    semantic_confidence: Mapped[float] = mapped_column(default=0.0)
    semantic_source: Mapped[str] = mapped_column(String(60), nullable=False)
    human_validated: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class CanonicalCaseRelationship(Base):
    """One discovered structural/operational relationship between two
    CanonicalCaseEntity rows in the same run. relationship_confidence is
    composed from both sides' entity_identity_confidence plus a distinct
    structural_evidence_confidence -- never from entity_type_confidence,
    and never a blind product (see app/entities/confidence_decomposition.py).
    relationship_type is evidence-gated, never inferred from the entity-
    type pair alone (plan review correction 2)."""

    __tablename__ = "canonical_case_relationships"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "analysis_case_id"],
            ["analysis_cases.organization_id", "analysis_cases.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "left_entity_id"],
            ["canonical_case_entities.organization_id", "canonical_case_entities.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "right_entity_id"],
            ["canonical_case_entities.organization_id", "canonical_case_entities.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "run_id",
            "left_entity_id",
            "right_entity_id",
            "relationship_type",
            name="uq_canonical_case_relationship_run_pair_type",
        ),
        CheckConstraint("left_entity_id != right_entity_id", name="ck_canonical_case_rel_no_self"),
        CheckConstraint(
            f"relationship_type IN ({enum_values(RelationshipType)})",
            name="ck_canonical_case_relationship_type",
        ),
        CheckConstraint(
            f"cardinality IN ({enum_values(Cardinality)})",
            name="ck_canonical_case_relationship_cardinality",
        ),
        CheckConstraint(
            f"status IN ({enum_values(RelationshipStatus)})",
            name="ck_canonical_case_relationship_status",
        ),
        Index(
            "ix_canonical_case_relationships_org_case_run",
            "organization_id",
            "analysis_case_id",
            "run_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    analysis_case_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("analysis_case_runs.id", ondelete="CASCADE"), nullable=False
    )
    left_entity_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    right_entity_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(30), nullable=False)
    cardinality: Mapped[str] = mapped_column(String(20), nullable=False)
    left_entity_identity_confidence: Mapped[float] = mapped_column(default=0.0)
    right_entity_identity_confidence: Mapped[float] = mapped_column(default=0.0)
    structural_evidence_confidence: Mapped[float] = mapped_column(default=0.0)
    relationship_confidence: Mapped[float] = mapped_column(default=0.0)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    evidence_summary: Mapped[list[str]] = mapped_column(portable_json, default=list)
    conflict_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    relationship_policy_version: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
