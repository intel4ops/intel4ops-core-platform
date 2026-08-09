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
    UniqueConstraint,
    Uuid,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.entities import portable_json, utc_now


class GroundedExecutiveNarrative(Base):
    __tablename__ = "grounded_executive_narratives"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "scan_id"],
            ["directional_value_scans.organization_id", "directional_value_scans.id"],
            name="fk_grounded_narratives_org_scan",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "profile_id"],
            ["ai_operational_profiles.organization_id", "ai_operational_profiles.id"],
            name="fk_grounded_narratives_org_profile",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "id", name="uq_grounded_narratives_org_id"),
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_grounded_narratives_org_idempotency",
        ),
        UniqueConstraint(
            "organization_id",
            "execution_fingerprint",
            name="uq_grounded_narratives_org_execution_fingerprint",
        ),
        CheckConstraint("audience = 'EXECUTIVE'", name="ck_grounded_narratives_audience"),
        CheckConstraint("status IN ('completed','fallback')", name="ck_grounded_narratives_status"),
        Index(
            "ix_grounded_narratives_org_generated",
            "organization_id",
            "generated_at",
        ),
        Index("ix_grounded_narratives_org_scan", "organization_id", "scan_id"),
        Index("ix_grounded_narratives_org_profile", "organization_id", "profile_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    scan_id: Mapped[UUID] = mapped_column(Uuid)
    profile_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    requested_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    idempotency_key: Mapped[str] = mapped_column(String(255))
    audience: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30))
    provider_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    model_code: Mapped[str | None] = mapped_column(String(150), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(150), nullable=True)
    template_code: Mapped[str] = mapped_column(String(100))
    template_version: Mapped[str] = mapped_column(String(30))
    schema_version: Mapped[str] = mapped_column(String(30))
    request_hash: Mapped[str] = mapped_column(String(64))
    input_fingerprint: Mapped[str] = mapped_column(String(64))
    execution_fingerprint: Mapped[str] = mapped_column(String(64))
    source_scan_content_hash: Mapped[str] = mapped_column(String(64))
    source_profile_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    structured_source_snapshot: Mapped[dict[str, object]] = mapped_column(portable_json)
    structured_narrative_snapshot: Mapped[dict[str, object]] = mapped_column(portable_json)
    limitations: Mapped[list[str]] = mapped_column(portable_json)
    observability_snapshot: Mapped[dict[str, object]] = mapped_column(portable_json)
    provider_failure_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


def _prevent_grounded_narrative_mutation(*_: object) -> None:
    raise ValueError("grounded executive narratives are immutable")


event.listen(GroundedExecutiveNarrative, "before_update", _prevent_grounded_narrative_mutation)
event.listen(GroundedExecutiveNarrative, "before_delete", _prevent_grounded_narrative_mutation)
