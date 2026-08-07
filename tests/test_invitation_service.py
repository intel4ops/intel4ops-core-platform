from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from app.models.access import AccessAuditEvent, InvitationStatus, OrganizationInvitation
from app.models.entities import (
    MembershipRole,
    MembershipStatus,
    Organization,
    OrganizationMembership,
    utc_now,
)
from app.schemas.access import InvitationCreate
from app.schemas.contracts import OrganizationCreate
from app.schemas.memberships import MembershipCreate
from app.services.invitation_service import (
    InvitationService,
    InvitationServiceError,
    _hash_token,
)
from app.services.membership_service import OrganizationMembershipService
from app.services.organization_service import OrganizationService


def create_organization(db: Session, slug: str) -> Organization:
    return OrganizationService().create(
        db,
        OrganizationCreate(
            name=slug,
            slug=slug,
            country_code="US",
            default_currency="USD",
            timezone="UTC",
        ),
    )


def create_membership(
    db: Session,
    organization_id: UUID,
    user_id: UUID,
    *,
    role: MembershipRole = MembershipRole.VIEWER,
    status: MembershipStatus = MembershipStatus.REVOKED,
) -> OrganizationMembership:
    return OrganizationMembershipService().create(
        db,
        organization_id,
        MembershipCreate(user_id=user_id, role=role, status=status),
        invited_by_user_id=uuid4(),
    )


def test_create_invitation_hashes_token_and_never_persists_it_plaintext(db: Session) -> None:
    service = InvitationService()
    organization = create_organization(db, "invitation-create")
    inviter = uuid4()

    invitation, token = service.create(
        db,
        organization.id,
        InvitationCreate(email="new.member@example.com", role=MembershipRole.ANALYST),
        invited_by_user_id=inviter,
    )

    assert invitation.status == InvitationStatus.PENDING.value
    assert invitation.token_hash == _hash_token(token)
    assert token not in invitation.token_hash
    stored = db.get(OrganizationInvitation, invitation.id)
    assert stored is not None
    assert stored.token_hash == _hash_token(token)


def test_create_invitation_rejects_duplicate_pending_email(db: Session) -> None:
    service = InvitationService()
    organization = create_organization(db, "invitation-duplicate")
    payload = InvitationCreate(email="dup@example.com", role=MembershipRole.VIEWER)

    service.create(db, organization.id, payload, invited_by_user_id=uuid4())
    with pytest.raises(InvitationServiceError) as excinfo:
        service.create(db, organization.id, payload, invited_by_user_id=uuid4())
    assert excinfo.value.code == "invitation_conflict"
    assert excinfo.value.status == 409


def test_create_invitation_organization_not_found(db: Session) -> None:
    service = InvitationService()
    with pytest.raises(InvitationServiceError) as excinfo:
        service.create(
            db,
            uuid4(),
            InvitationCreate(email="ghost@example.com", role=MembershipRole.VIEWER),
            invited_by_user_id=uuid4(),
        )
    assert excinfo.value.code == "organization_not_found"
    assert excinfo.value.status == 404


def test_revoke_invitation_lifecycle(db: Session) -> None:
    service = InvitationService()
    organization = create_organization(db, "invitation-revoke")
    invitation, _ = service.create(
        db,
        organization.id,
        InvitationCreate(email="revoke@example.com", role=MembershipRole.VIEWER),
        invited_by_user_id=uuid4(),
    )

    revoked = service.revoke(db, organization.id, invitation.id, uuid4())
    assert revoked.status == InvitationStatus.REVOKED.value

    with pytest.raises(InvitationServiceError) as excinfo:
        service.revoke(db, organization.id, invitation.id, uuid4())
    assert excinfo.value.code == "invitation_conflict"

    with pytest.raises(InvitationServiceError) as excinfo:
        service.revoke(db, organization.id, uuid4(), uuid4())
    assert excinfo.value.code == "invitation_not_found_or_invalid"


def test_accept_invitation_creates_active_membership_with_invitation_role(db: Session) -> None:
    service = InvitationService()
    organization = create_organization(db, "invitation-accept")
    invitation, token = service.create(
        db,
        organization.id,
        InvitationCreate(email="accept@example.com", role=MembershipRole.RECOVERY_MANAGER),
        invited_by_user_id=uuid4(),
    )
    accepting_user = uuid4()

    membership = service.accept(db, token, accepting_user)

    assert membership.organization_id == organization.id
    assert membership.user_id == accepting_user
    assert membership.role == MembershipRole.RECOVERY_MANAGER.value
    assert membership.status == MembershipStatus.ACTIVE.value

    refreshed_invitation = db.get(OrganizationInvitation, invitation.id)
    assert refreshed_invitation is not None
    assert refreshed_invitation.status == InvitationStatus.ACCEPTED.value
    assert refreshed_invitation.accepted_by_user_id == accepting_user
    assert refreshed_invitation.resulting_membership_id == membership.id


def test_accept_invitation_reactivates_existing_revoked_membership(db: Session) -> None:
    service = InvitationService()
    organization = create_organization(db, "invitation-reactivate")
    accepting_user = uuid4()
    existing = create_membership(
        db,
        organization.id,
        accepting_user,
        role=MembershipRole.VIEWER,
        status=MembershipStatus.REVOKED,
    )
    _, token = service.create(
        db,
        organization.id,
        InvitationCreate(email="reactivate@example.com", role=MembershipRole.OPERATOR),
        invited_by_user_id=uuid4(),
    )

    membership = service.accept(db, token, accepting_user)

    assert membership.id == existing.id
    assert membership.role == MembershipRole.OPERATOR.value
    assert membership.status == MembershipStatus.ACTIVE.value


def test_accept_invalid_token_raises_not_found(db: Session) -> None:
    service = InvitationService()
    with pytest.raises(InvitationServiceError) as excinfo:
        service.accept(db, "not-a-real-token", uuid4())
    assert excinfo.value.code == "invitation_not_found_or_invalid"
    assert excinfo.value.status == 404


def test_accept_revoked_invitation_raises_conflict(db: Session) -> None:
    service = InvitationService()
    organization = create_organization(db, "invitation-accept-revoked")
    invitation, token = service.create(
        db,
        organization.id,
        InvitationCreate(email="revoked-accept@example.com", role=MembershipRole.VIEWER),
        invited_by_user_id=uuid4(),
    )
    service.revoke(db, organization.id, invitation.id, uuid4())

    with pytest.raises(InvitationServiceError) as excinfo:
        service.accept(db, token, uuid4())
    assert excinfo.value.code == "invitation_revoked"
    assert excinfo.value.status == 409


def test_accept_expired_invitation_flips_status_and_raises(db: Session) -> None:
    service = InvitationService()
    organization = create_organization(db, "invitation-expired")
    invitation, token = service.create(
        db,
        organization.id,
        InvitationCreate(email="expired@example.com", role=MembershipRole.VIEWER),
        invited_by_user_id=uuid4(),
    )
    invitation.expires_at = utc_now() - timedelta(seconds=1)
    db.commit()

    with pytest.raises(InvitationServiceError) as excinfo:
        service.accept(db, token, uuid4())
    assert excinfo.value.code == "invitation_expired"
    assert excinfo.value.status == 409

    refreshed = db.get(OrganizationInvitation, invitation.id)
    assert refreshed is not None
    assert refreshed.status == InvitationStatus.EXPIRED.value


def test_accept_is_idempotent_for_same_accepting_user(db: Session) -> None:
    service = InvitationService()
    organization = create_organization(db, "invitation-idempotent")
    _, token = service.create(
        db,
        organization.id,
        InvitationCreate(email="idempotent@example.com", role=MembershipRole.VIEWER),
        invited_by_user_id=uuid4(),
    )
    accepting_user = uuid4()

    first = service.accept(db, token, accepting_user)
    second = service.accept(db, token, accepting_user)
    assert first.id == second.id


def test_accept_already_accepted_by_different_user_raises_conflict(db: Session) -> None:
    service = InvitationService()
    organization = create_organization(db, "invitation-cross-user")
    _, token = service.create(
        db,
        organization.id,
        InvitationCreate(email="cross-user@example.com", role=MembershipRole.VIEWER),
        invited_by_user_id=uuid4(),
    )
    service.accept(db, token, uuid4())

    with pytest.raises(InvitationServiceError) as excinfo:
        service.accept(db, token, uuid4())
    assert excinfo.value.code == "invitation_conflict"
    assert excinfo.value.status == 409


def test_list_invitations_filters_by_status(db: Session) -> None:
    service = InvitationService()
    organization = create_organization(db, "invitation-list")
    pending, _ = service.create(
        db,
        organization.id,
        InvitationCreate(email="pending@example.com", role=MembershipRole.VIEWER),
        invited_by_user_id=uuid4(),
    )
    revoked, _ = service.create(
        db,
        organization.id,
        InvitationCreate(email="to-revoke@example.com", role=MembershipRole.VIEWER),
        invited_by_user_id=uuid4(),
    )
    service.revoke(db, organization.id, revoked.id, uuid4())

    all_invitations = service.list(db, organization.id)
    assert {item.id for item in all_invitations} == {pending.id, revoked.id}

    only_pending = service.list(db, organization.id, status=InvitationStatus.PENDING)
    assert [item.id for item in only_pending] == [pending.id]


def test_terminal_invitation_is_immutable(db: Session) -> None:
    service = InvitationService()
    organization = create_organization(db, "invitation-immutable")
    invitation, _ = service.create(
        db,
        organization.id,
        InvitationCreate(email="immutable@example.com", role=MembershipRole.VIEWER),
        invited_by_user_id=uuid4(),
    )
    service.revoke(db, organization.id, invitation.id, uuid4())

    invitation.email = "changed@example.com"
    with pytest.raises(ValueError, match="immutable"):
        db.commit()
    db.rollback()


def test_access_audit_event_is_immutable(db: Session) -> None:
    organization = create_organization(db, "audit-immutable")
    event = AccessAuditEvent(
        organization_id=organization.id,
        event_type="test_event",
        entity_type="organization",
        entity_id=organization.id,
        actor_user_id=uuid4(),
        summary="probe",
    )
    db.add(event)
    db.commit()

    event.summary = "mutated"
    with pytest.raises(ValueError, match="immutable"):
        db.commit()
    db.rollback()

    refetched = db.get(AccessAuditEvent, event.id)
    assert refetched is not None
    db.delete(refetched)
    with pytest.raises(ValueError, match="immutable"):
        db.commit()
    db.rollback()
