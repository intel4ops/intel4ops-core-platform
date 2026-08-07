from __future__ import annotations

from datetime import datetime
from enum import StrEnum
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
    event,
    inspect,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.entities import MembershipRole, portable_json, utc_now
from app.models.source_system import enum_values


class InvitationStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    EXPIRED = "expired"
    REVOKED = "revoked"


INVITATION_TERMINAL_STATUSES = {
    InvitationStatus.ACCEPTED.value,
    InvitationStatus.EXPIRED.value,
    InvitationStatus.REVOKED.value,
}


class OrganizationInvitation(Base):
    __tablename__ = "organization_invitations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "resulting_membership_id"],
            ["organization_members.organization_id", "organization_members.id"],
            name="fk_organization_invitations_org_membership",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "id", name="uq_organization_invitations_org_id"),
        CheckConstraint(
            f"role IN ({enum_values(MembershipRole)})",
            name="ck_organization_invitation_role",
        ),
        CheckConstraint(
            f"status IN ({enum_values(InvitationStatus)})",
            name="ck_organization_invitation_status",
        ),
        CheckConstraint(
            "status <> 'accepted' OR (accepted_at IS NOT NULL AND accepted_by_user_id IS NOT NULL "
            "AND resulting_membership_id IS NOT NULL)",
            name="ck_organization_invitation_acceptance",
        ),
        Index(
            "ux_organization_invitations_org_email_pending",
            "organization_id",
            "email",
            unique=True,
            postgresql_where=text("status = 'pending'"),
            sqlite_where=text("status = 'pending'"),
        ),
        Index("ix_organization_invitations_org_status", "organization_id", "status"),
        UniqueConstraint(
            "token_hash", name="uq_organization_invitations_token_hash"
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    email: Mapped[str] = mapped_column(String(320))
    role: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), default=InvitationStatus.PENDING.value)
    token_hash: Mapped[str] = mapped_column(String(64))
    invited_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    resulting_membership_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class AccessAuditEvent(Base):
    __tablename__ = "access_audit_events"
    __table_args__ = (
        Index("ix_access_audit_org_time", "organization_id", "occurred_at"),
        Index("ix_access_audit_org_entity", "organization_id", "entity_type", "entity_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    event_type: Mapped[str] = mapped_column(String(60))
    entity_type: Mapped[str] = mapped_column(String(60))
    entity_id: Mapped[UUID] = mapped_column(Uuid)
    actor_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


def _guard_terminal_invitation(
    _mapper: object, _connection: object, target: OrganizationInvitation
) -> None:
    state = inspect(target)
    prior = state.attrs.status.history.deleted
    prior_status = prior[0] if prior else target.status
    if prior_status in INVITATION_TERMINAL_STATUSES:
        raise ValueError("terminal organization invitations are immutable")


def _guard_terminal_invitation_delete(
    _mapper: object, _connection: object, target: OrganizationInvitation
) -> None:
    if target.status in INVITATION_TERMINAL_STATUSES:
        raise ValueError("terminal organization invitations are immutable")


def _immutable(*_: object) -> None:
    raise ValueError("access audit events are immutable")


event.listen(OrganizationInvitation, "before_update", _guard_terminal_invitation)
event.listen(OrganizationInvitation, "before_delete", _guard_terminal_invitation_delete)
event.listen(AccessAuditEvent, "before_update", _immutable)
event.listen(AccessAuditEvent, "before_delete", _immutable)
