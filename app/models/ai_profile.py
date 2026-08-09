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
    event,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm.attributes import instance_state

from app.db.session import Base
from app.models.entities import portable_json, utc_now

PROFILE_STATUSES = ("running", "completed", "partial", "failed", "unavailable")
INFERENCE_STATUSES = (
    "INFERRED",
    "CONFIRMED",
    "CORRECTED",
    "REJECTED",
    "DEFERRED",
    "SUPERSEDED",
)


class AIOperationalProfile(Base):
    __tablename__ = "ai_operational_profiles"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_ai_operational_profiles_org_id"),
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_ai_operational_profiles_org_idempotency",
        ),
        UniqueConstraint(
            "organization_id",
            "execution_fingerprint",
            name="uq_ai_operational_profiles_org_execution_fingerprint",
        ),
        CheckConstraint(
            "status IN ('running','completed','partial','failed','unavailable')",
            name="ck_ai_operational_profiles_status",
        ),
        Index("ix_ai_operational_profiles_org_generated", "organization_id", "generated_at"),
        Index("ix_ai_operational_profiles_org_status", "organization_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    requested_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    idempotency_key: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(30))
    provider_code: Mapped[str] = mapped_column(String(60))
    model_code: Mapped[str] = mapped_column(String(150))
    model_version: Mapped[str | None] = mapped_column(String(150), nullable=True)
    template_code: Mapped[str] = mapped_column(String(100))
    template_version: Mapped[str] = mapped_column(String(30))
    input_fingerprint: Mapped[str] = mapped_column(String(64))
    execution_fingerprint: Mapped[str] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64))
    response_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    profile_summary_snapshot: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    input_provenance_snapshot: Mapped[dict[str, object]] = mapped_column(
        portable_json, default=dict
    )
    observability_snapshot: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    limitations: Mapped[list[str]] = mapped_column(portable_json, default=list)
    failure_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    failure_message_sanitized: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AIProfileInference(Base):
    __tablename__ = "ai_profile_inferences"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "profile_id"],
            ["ai_operational_profiles.organization_id", "ai_operational_profiles.id"],
            name="fk_ai_profile_inferences_org_profile",
            ondelete="CASCADE",
        ),
        UniqueConstraint("organization_id", "id", name="uq_ai_profile_inferences_org_id"),
        UniqueConstraint(
            "profile_id",
            "sequence_number",
            name="uq_ai_profile_inferences_profile_sequence",
        ),
        CheckConstraint(
            "confidence IN ('HIGH','MEDIUM','LOW')",
            name="ck_ai_profile_inferences_confidence",
        ),
        CheckConstraint(
            "status IN ('INFERRED','CONFIRMED','CORRECTED','REJECTED','DEFERRED','SUPERSEDED')",
            name="ck_ai_profile_inferences_status",
        ),
        CheckConstraint("sequence_number > 0", name="ck_ai_profile_inferences_sequence"),
        Index("ix_ai_profile_inferences_org_profile", "organization_id", "profile_id"),
        Index("ix_ai_profile_inferences_org_status", "organization_id", "status"),
        Index("ix_ai_profile_inferences_org_type", "organization_id", "inference_type"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    profile_id: Mapped[UUID] = mapped_column(Uuid)
    sequence_number: Mapped[int] = mapped_column(Integer)
    inference_type: Mapped[str] = mapped_column(String(60))
    proposed_code: Mapped[str | None] = mapped_column(String(150), nullable=True)
    proposed_value: Mapped[str | None] = mapped_column(String(500), nullable=True)
    display_value: Mapped[str | None] = mapped_column(String(500), nullable=True)
    confidence: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(30), default="INFERRED")
    reasoning_summary: Mapped[str] = mapped_column(String(500))
    evidence_references: Mapped[list[str]] = mapped_column(portable_json, default=list)
    alternative_candidates: Mapped[list[str]] = mapped_column(portable_json, default=list)
    provider_metadata: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    confirmed_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deferred_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    deferred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    corrected_code: Mapped[str | None] = mapped_column(String(150), nullable=True)
    corrected_value: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


def _protect_terminal_profile(_mapper: object, _connection: object, target: object) -> None:
    state = instance_state(target)
    history = state.attrs.status.history
    prior = history.deleted[0] if history.deleted else None
    if prior in {"completed", "partial", "failed", "unavailable"}:
        raise ValueError("terminal AI operational profiles are immutable")


event.listen(AIOperationalProfile, "before_update", _protect_terminal_profile)
