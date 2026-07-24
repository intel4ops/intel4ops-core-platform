from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.models.entities import (
    MembershipRole,
    MembershipStatus,
    Organization,
    OrganizationMembership,
)
from app.schemas.contracts import OrganizationCreate
from app.schemas.memberships import MembershipCreate
from app.services.membership_service import (
    DuplicateMembershipError,
    LastActiveOrganizationAdminError,
    MembershipAuthorizationError,
    MembershipNotFoundError,
    MembershipOrganizationNotFoundError,
    OrganizationMembershipService,
)
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
    *,
    role: MembershipRole = MembershipRole.VIEWER,
    status: MembershipStatus = MembershipStatus.INVITED,
) -> OrganizationMembership:
    return OrganizationMembershipService().create(
        db,
        organization_id,
        MembershipCreate(user_id=uuid4(), role=role, status=status),
        invited_by_user_id=uuid4(),
    )


def test_membership_create_duplicate_and_organization_validation(db: Session) -> None:
    service = OrganizationMembershipService()
    organization = create_organization(db, "membership-create")
    user_id = uuid4()
    payload = MembershipCreate(user_id=user_id, role=MembershipRole.ANALYST)

    membership = service.create(db, organization.id, payload, invited_by_user_id=uuid4())
    assert membership.status == MembershipStatus.INVITED.value
    assert membership.joined_at is None

    with pytest.raises(DuplicateMembershipError):
        service.create(db, organization.id, payload, invited_by_user_id=uuid4())
    with pytest.raises(MembershipOrganizationNotFoundError):
        service.create(db, uuid4(), payload, invited_by_user_id=uuid4())


def test_invalid_role_and_status_are_rejected() -> None:
    with pytest.raises(ValidationError):
        MembershipCreate.model_validate({"user_id": uuid4(), "role": "owner"})
    with pytest.raises(ValidationError):
        MembershipCreate.model_validate(
            {
                "user_id": uuid4(),
                "role": MembershipRole.VIEWER.value,
                "status": "disabled",
            }
        )


def test_membership_lifecycle_and_authorization(db: Session) -> None:
    service = OrganizationMembershipService()
    organization = create_organization(db, "membership-lifecycle")
    membership = create_membership(db, organization.id)

    with pytest.raises(MembershipAuthorizationError):
        service.require_active_member(db, organization.id, membership.user_id)

    activated = service.activate(db, organization.id, membership.id)
    assert activated.status == MembershipStatus.ACTIVE.value
    assert activated.joined_at is not None
    joined_at = activated.joined_at
    assert service.activate(db, organization.id, membership.id).joined_at == joined_at
    assert (
        service.require_roles(
            db,
            organization.id,
            membership.user_id,
            {MembershipRole.VIEWER},
        ).id
        == membership.id
    )

    with pytest.raises(MembershipAuthorizationError):
        service.require_roles(
            db,
            organization.id,
            membership.user_id,
            {MembershipRole.ORGANIZATION_ADMIN},
        )

    suspended = service.suspend(db, organization.id, membership.id)
    assert suspended.status == MembershipStatus.SUSPENDED.value
    with pytest.raises(MembershipAuthorizationError):
        service.require_active_member(db, organization.id, membership.user_id)

    service.activate(db, organization.id, membership.id)
    revoked = service.revoke(db, organization.id, membership.id)
    assert revoked.status == MembershipStatus.REVOKED.value
    with pytest.raises(MembershipAuthorizationError):
        service.require_active_member(db, organization.id, membership.user_id)


@pytest.mark.parametrize("operation", ["demote", "suspend", "revoke"])
def test_last_active_admin_is_protected(db: Session, operation: str) -> None:
    service = OrganizationMembershipService()
    organization = create_organization(db, f"last-admin-{operation}")
    admin = create_membership(
        db,
        organization.id,
        role=MembershipRole.ORGANIZATION_ADMIN,
        status=MembershipStatus.ACTIVE,
    )

    with pytest.raises(LastActiveOrganizationAdminError):
        if operation == "demote":
            service.update_role(db, organization.id, admin.id, MembershipRole.ANALYST)
        elif operation == "suspend":
            service.suspend(db, organization.id, admin.id)
        else:
            service.revoke(db, organization.id, admin.id)


def test_multiple_admins_allow_change_and_cross_organization_lookup_is_hidden(
    db: Session,
) -> None:
    service = OrganizationMembershipService()
    first = create_organization(db, "multiple-admins-first")
    second = create_organization(db, "multiple-admins-second")
    first_admin = create_membership(
        db,
        first.id,
        role=MembershipRole.ORGANIZATION_ADMIN,
        status=MembershipStatus.ACTIVE,
    )
    create_membership(
        db,
        first.id,
        role=MembershipRole.ORGANIZATION_ADMIN,
        status=MembershipStatus.ACTIVE,
    )

    changed = service.update_role(db, first.id, first_admin.id, MembershipRole.ANALYST)
    assert changed.role == MembershipRole.ANALYST.value
    with pytest.raises(MembershipNotFoundError):
        service.get(db, second.id, first_admin.id)
