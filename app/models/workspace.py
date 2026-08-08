from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.entities import utc_now


class OrganizationObjective(Base):
    """A business priority the organization has selected for itself.

    Mutable customer preference, not a governed/audited record: selecting
    adds a row, deselecting removes it. objective_code is validated against
    app.registries.objective_registry at the service layer, not by a
    database CHECK, since the registry is expected to grow.
    """

    __tablename__ = "organization_objectives"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "objective_code", name="uq_organization_objectives_org_code"
        ),
        Index("ix_organization_objectives_org", "organization_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    objective_code: Mapped[str] = mapped_column(String(60))
    selected_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    selected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class OrganizationChallenge(Base):
    """A perceived operational challenge the organization has explicitly
    stated. Never inferred from objective selections. Mutable, same shape
    and lifecycle as OrganizationObjective."""

    __tablename__ = "organization_challenges"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "challenge_code", name="uq_organization_challenges_org_code"
        ),
        Index("ix_organization_challenges_org", "organization_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    challenge_code: Mapped[str] = mapped_column(String(60))
    selected_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    selected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class OrganizationSystem(Base):
    """A system the organization has declared it uses. Metadata only: no
    credentials, no endpoints, no connection state -- Connect owns all of
    that later. custom_label is nullable at the database level; the
    (organization_id, system_code, custom_label) unique constraint alone
    cannot prevent two NULL-custom_label rows for the same known system
    (SQL treats NULL as distinct from NULL), so the service layer also
    rejects a duplicate system_code selection for non-custom registry
    entries before insert.
    """

    __tablename__ = "organization_systems"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "system_code",
            "custom_label",
            name="uq_organization_systems_org_code_label",
        ),
        Index("ix_organization_systems_org", "organization_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    system_code: Mapped[str] = mapped_column(String(60))
    custom_label: Mapped[str | None] = mapped_column(String(150), nullable=True)
    selected_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    selected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
