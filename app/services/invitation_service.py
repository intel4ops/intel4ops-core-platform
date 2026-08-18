import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.access import AccessAuditEvent, InvitationStatus, OrganizationInvitation
from app.models.entities import (
    MembershipStatus,
    Organization,
    OrganizationMembership,
    utc_now,
)
from app.schemas.access import InvitationCreate

# Governed default: how long an invitation remains acceptable after creation.
INVITATION_EXPIRY = timedelta(days=7)


class InvitationServiceError(ValueError):
    def __init__(self, message: str, *, code: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


def record_access_audit_event(
    db: Session,
    organization_id: UUID,
    event_type: str,
    entity_type: str,
    entity_id: UUID,
    actor_user_id: UUID | None,
    summary: str,
    metadata: dict[str, object] | None = None,
) -> AccessAuditEvent:
    """Shared audit-event writer for both invitation and membership mutations.

    Never pass raw tokens, credentials, or JWTs in `summary`/`metadata` --
    this table is append-only and readable by organization admins.
    """
    event = AccessAuditEvent(
        organization_id=organization_id,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_user_id=actor_user_id,
        summary=summary,
        metadata_json=metadata or {},
    )
    db.add(event)
    return event


def _utc_datetime(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class InvitationService:
    def create(
        self,
        db: Session,
        organization_id: UUID,
        payload: InvitationCreate,
        invited_by_user_id: UUID,
    ) -> tuple[OrganizationInvitation, str]:
        if db.get(Organization, organization_id) is None:
            raise InvitationServiceError(
                "Organization not found", code="organization_not_found", status=404
            )
        email = _normalize_email(payload.email)
        existing = db.scalar(
            select(OrganizationInvitation).where(
                OrganizationInvitation.organization_id == organization_id,
                OrganizationInvitation.email == email,
                OrganizationInvitation.status == InvitationStatus.PENDING.value,
            )
        )
        if existing is not None:
            raise InvitationServiceError(
                "A pending invitation already exists for this email",
                code="invitation_conflict",
                status=409,
            )
        token = secrets.token_urlsafe(32)
        invitation = OrganizationInvitation(
            organization_id=organization_id,
            email=email,
            role=payload.role.value,
            status=InvitationStatus.PENDING.value,
            token_hash=_hash_token(token),
            invited_by_user_id=invited_by_user_id,
            expires_at=utc_now() + INVITATION_EXPIRY,
        )
        db.add(invitation)
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise InvitationServiceError(
                "A pending invitation already exists for this email",
                code="invitation_conflict",
                status=409,
            ) from exc
        record_access_audit_event(
            db,
            organization_id,
            "invitation_created",
            "organization_invitation",
            invitation.id,
            invited_by_user_id,
            f"Invitation created for role {invitation.role}",
        )
        db.commit()
        db.refresh(invitation)
        return invitation, token

    def list(
        self, db: Session, organization_id: UUID, *, status: InvitationStatus | None = None
    ) -> list[OrganizationInvitation]:
        statement = select(OrganizationInvitation).where(
            OrganizationInvitation.organization_id == organization_id
        )
        if status is not None:
            statement = statement.where(OrganizationInvitation.status == status.value)
        statement = statement.order_by(OrganizationInvitation.created_at.desc())
        return list(db.scalars(statement).all())

    def revoke(
        self, db: Session, organization_id: UUID, invitation_id: UUID, actor_user_id: UUID
    ) -> OrganizationInvitation:
        invitation = db.scalar(
            select(OrganizationInvitation)
            .where(
                OrganizationInvitation.id == invitation_id,
                OrganizationInvitation.organization_id == organization_id,
            )
            .with_for_update()
        )
        if invitation is None:
            raise InvitationServiceError(
                "Invitation not found", code="invitation_not_found_or_invalid", status=404
            )
        if invitation.status != InvitationStatus.PENDING.value:
            raise InvitationServiceError(
                "Only a pending invitation can be revoked",
                code="invitation_conflict",
                status=409,
            )
        invitation.status = InvitationStatus.REVOKED.value
        record_access_audit_event(
            db,
            organization_id,
            "invitation_revoked",
            "organization_invitation",
            invitation.id,
            actor_user_id,
            "Invitation revoked",
        )
        db.commit()
        db.refresh(invitation)
        return invitation

    def accept(
        self,
        db: Session,
        token: str,
        accepting_user_id: UUID,
        accepting_email: str | None,
        accepting_email_verified: bool,
    ) -> OrganizationMembership:
        token_hash = _hash_token(token)
        invitation = db.scalar(
            select(OrganizationInvitation)
            .where(OrganizationInvitation.token_hash == token_hash)
            .with_for_update()
        )
        if invitation is None:
            raise InvitationServiceError(
                "Invitation token is not valid",
                code="invitation_not_found_or_invalid",
                status=404,
            )
        if invitation.status == InvitationStatus.ACCEPTED.value:
            if invitation.accepted_by_user_id == accepting_user_id:
                membership = db.get(OrganizationMembership, invitation.resulting_membership_id)
                if membership is not None:
                    return membership
            raise InvitationServiceError(
                "Invitation has already been accepted",
                code="invitation_conflict",
                status=409,
            )
        if invitation.status == InvitationStatus.REVOKED.value:
            raise InvitationServiceError(
                "Invitation has been revoked", code="invitation_revoked", status=409
            )
        if invitation.status == InvitationStatus.EXPIRED.value or (
            _utc_datetime(invitation.expires_at) <= utc_now()
        ):
            if invitation.status == InvitationStatus.PENDING.value:
                invitation.status = InvitationStatus.EXPIRED.value
                db.commit()
            raise InvitationServiceError(
                "Invitation has expired", code="invitation_expired", status=409
            )

        # Recipient binding: an invitation is issued to a specific email
        # recipient, and possession of the token alone is not sufficient
        # authorization to redeem it. Checked only for a still-PENDING
        # invitation with no matching branch above, so this never fires for
        # the already-accepted/revoked/expired cases, and -- critically --
        # does not mutate or consume the invitation: the intended recipient
        # can still redeem the same token after a mismatched attempt. Does
        # not distinguish "no email claim" / "unverified" / "wrong email" in
        # the response, so a caller can't use this endpoint to probe which
        # of those is true for a token they don't legitimately own.
        if (
            not accepting_email
            or not accepting_email_verified
            or _normalize_email(accepting_email) != invitation.email
        ):
            raise InvitationServiceError(
                "This invitation is not available to your authenticated identity",
                code="invitation_recipient_mismatch",
                status=403,
            )

        organization_id = invitation.organization_id
        membership = db.scalar(
            select(OrganizationMembership)
            .where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.user_id == accepting_user_id,
            )
            .with_for_update()
        )
        if membership is None:
            membership = OrganizationMembership(
                organization_id=organization_id,
                user_id=accepting_user_id,
                role=invitation.role,
                status=MembershipStatus.ACTIVE.value,
                invited_by_user_id=invitation.invited_by_user_id,
                joined_at=utc_now(),
            )
            db.add(membership)
        else:
            membership.role = invitation.role
            membership.status = MembershipStatus.ACTIVE.value
            if membership.joined_at is None:
                membership.joined_at = utc_now()
        db.flush()

        invitation.status = InvitationStatus.ACCEPTED.value
        invitation.accepted_at = utc_now()
        invitation.accepted_by_user_id = accepting_user_id
        invitation.resulting_membership_id = membership.id

        record_access_audit_event(
            db,
            organization_id,
            "invitation_accepted",
            "organization_invitation",
            invitation.id,
            accepting_user_id,
            f"Invitation accepted, membership role {membership.role}",
        )
        db.commit()
        db.refresh(membership)
        return membership


invitation_service = InvitationService()
