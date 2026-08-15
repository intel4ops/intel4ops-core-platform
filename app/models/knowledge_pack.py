from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.entities import utc_now
from app.models.source_system import portable_json

PACK_VERSION_STATUSES = (
    "draft",
    "in_review",
    "approved",
    "rejected",
    "superseded",
    "retired",
)
PACK_PROVENANCE_TYPES = ("production", "simulation", "manual", "mixed")


class KnowledgePack(Base):
    __tablename__ = "knowledge_packs"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_knowledge_pack_org_id"),
        UniqueConstraint("organization_id", "slug", name="uq_knowledge_pack_org_slug"),
        Index("ix_knowledge_pack_org_domain", "organization_id", "domain", "industry"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    name: Mapped[str] = mapped_column(String(250))
    slug: Mapped[str] = mapped_column(String(150))
    description: Mapped[str] = mapped_column(Text)
    industry: Mapped[str] = mapped_column(String(100))
    domain: Mapped[str] = mapped_column(String(100))
    scope: Mapped[str] = mapped_column(Text)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class KnowledgePackVersion(Base):
    __tablename__ = "knowledge_pack_versions"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_knowledge_pack_version_org_id"),
        UniqueConstraint("knowledge_pack_id", "version_number", name="uq_pack_version_number"),
        ForeignKeyConstraint(
            ["organization_id", "knowledge_pack_id"],
            ["knowledge_packs.organization_id", "knowledge_packs.id"],
            name="fk_pack_version_org_pack",
            ondelete="CASCADE",
        ),
        CheckConstraint("version_number > 0", name="ck_pack_version_positive"),
        CheckConstraint(
            f"lifecycle_status IN {PACK_VERSION_STATUSES}", name="ck_pack_version_status"
        ),
        CheckConstraint(
            f"provenance_summary IS NULL OR provenance_summary IN {PACK_PROVENANCE_TYPES}",
            name="ck_pack_version_provenance",
        ),
        Index(
            "ix_pack_version_org_pack_status",
            "organization_id",
            "knowledge_pack_id",
            "lifecycle_status",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    knowledge_pack_id: Mapped[UUID] = mapped_column(Uuid)
    version_number: Mapped[int] = mapped_column(Integer)
    lifecycle_status: Mapped[str] = mapped_column(String(20), default="draft")
    change_summary: Mapped[str] = mapped_column(Text)
    provenance_summary: Mapped[str | None] = mapped_column(String(20))
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    reviewed_by_user_id: Mapped[UUID | None] = mapped_column(Uuid)
    approved_by_user_id: Mapped[UUID | None] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class KnowledgePackLearningLink(Base):
    __tablename__ = "knowledge_pack_learning_links"
    __table_args__ = (
        UniqueConstraint(
            "knowledge_pack_version_id",
            "operational_learning_id",
            name="uq_pack_version_learning",
        ),
        ForeignKeyConstraint(
            ["organization_id", "knowledge_pack_version_id"],
            ["knowledge_pack_versions.organization_id", "knowledge_pack_versions.id"],
            name="fk_pack_learning_org_version",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "operational_learning_id"],
            ["operational_learnings.organization_id", "operational_learnings.id"],
            name="fk_pack_learning_org_learning",
            ondelete="RESTRICT",
        ),
        Index("ix_pack_learning_org_version", "organization_id", "knowledge_pack_version_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    knowledge_pack_version_id: Mapped[UUID] = mapped_column(Uuid)
    operational_learning_id: Mapped[UUID] = mapped_column(Uuid)
    inclusion_rationale: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class KnowledgePackAuditEvent(Base):
    __tablename__ = "knowledge_pack_audit_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "knowledge_pack_id"],
            ["knowledge_packs.organization_id", "knowledge_packs.id"],
            name="fk_pack_audit_org_pack",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "organization_id",
            "knowledge_pack_id",
            "sequence",
            name="uq_pack_audit_org_pack_sequence",
        ),
        CheckConstraint("sequence > 0", name="ck_pack_audit_sequence_positive"),
        Index("ix_pack_audit_org_pack_time", "organization_id", "knowledge_pack_id", "occurred_at"),
        Index(
            "ix_pack_audit_org_pack_sequence", "organization_id", "knowledge_pack_id", "sequence"
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    knowledge_pack_id: Mapped[UUID] = mapped_column(Uuid)
    knowledge_pack_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("knowledge_pack_versions.id", ondelete="SET NULL")
    )
    event_type: Mapped[str] = mapped_column(String(50))
    prior_status: Mapped[str | None] = mapped_column(String(20))
    new_status: Mapped[str | None] = mapped_column(String(20))
    actor_user_id: Mapped[UUID] = mapped_column(Uuid)
    actor_role: Mapped[str] = mapped_column(String(50))
    rationale: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    # Deterministic, service-assigned monotonic order within a pack. occurred_at alone
    # cannot guarantee ordering when two events are recorded within the same timestamp
    # resolution window; sequence is the authoritative read-order key.
    sequence: Mapped[int] = mapped_column(Integer)
