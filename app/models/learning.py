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
from app.models.entities import utc_now
from app.models.source_system import portable_json

LEARNING_TYPES = (
    "operational_pattern",
    "corrective_action",
    "causal_observation",
    "execution_playbook",
    "risk_indicator",
    "verification_pattern",
)
LEARNING_STATUSES = ("candidate", "reviewed", "approved_for_reuse", "rejected", "retired")
PROVENANCE_TYPES = ("production", "simulation", "manual", "mixed")
VALUE_BASES = ("none", "expected", "realized_measurement", "verified_ledger")


class OperationalLearning(Base):
    __tablename__ = "operational_learnings"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_operational_learning_org_id"),
        CheckConstraint(f"learning_type IN {LEARNING_TYPES}", name="ck_learning_type"),
        CheckConstraint(f"status IN {LEARNING_STATUSES}", name="ck_learning_status"),
        CheckConstraint(f"provenance_type IN {PROVENANCE_TYPES}", name="ck_learning_provenance"),
        CheckConstraint(f"value_basis IN {VALUE_BASES}", name="ck_learning_value_basis"),
        Index("ix_learning_org_status_created", "organization_id", "status", "created_at"),
        Index("ix_learning_org_provenance", "organization_id", "provenance_type"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    learning_type: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(250))
    statement: Mapped[str] = mapped_column(Text)
    scope: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="candidate")
    provenance_type: Mapped[str] = mapped_column(String(20))
    value_basis: Mapped[str] = mapped_column(String(30), default="none")
    rationale: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    reviewed_by_user_id: Mapped[UUID | None] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class LearningSourceCase(Base):
    __tablename__ = "learning_source_cases"
    __table_args__ = (
        UniqueConstraint("learning_id", "finding_id", name="uq_learning_source_case"),
        ForeignKeyConstraint(
            ["organization_id", "learning_id"],
            ["operational_learnings.organization_id", "operational_learnings.id"],
            name="fk_learning_source_org_learning",
            ondelete="CASCADE",
        ),
        Index("ix_learning_source_org_finding", "organization_id", "finding_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    learning_id: Mapped[UUID] = mapped_column(Uuid)
    finding_id: Mapped[UUID] = mapped_column(ForeignKey("findings.id", ondelete="RESTRICT"))
    provenance_type: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class LearningAuditEvent(Base):
    __tablename__ = "learning_audit_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "learning_id"],
            ["operational_learnings.organization_id", "operational_learnings.id"],
            name="fk_learning_audit_org_learning",
            ondelete="CASCADE",
        ),
        Index("ix_learning_audit_org_learning", "organization_id", "learning_id", "occurred_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    learning_id: Mapped[UUID] = mapped_column(Uuid)
    event_type: Mapped[str] = mapped_column(String(50))
    prior_status: Mapped[str | None] = mapped_column(String(30))
    new_status: Mapped[str] = mapped_column(String(30))
    actor_user_id: Mapped[UUID] = mapped_column(Uuid)
    actor_role: Mapped[str] = mapped_column(String(50))
    rationale: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
