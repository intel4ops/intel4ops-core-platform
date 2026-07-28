from uuid import UUID, uuid4

from conftest import IdentityState
from fastapi.testclient import TestClient
from pydantic import TypeAdapter
from sqlalchemy.orm import Session

from app.models.entities import MembershipRole, MembershipStatus
from app.schemas.contracts import FindingCreate, OrganizationCreate
from app.schemas.memberships import MembershipCreate
from app.services.finding_service import FindingService
from app.services.membership_service import OrganizationMembershipService
from app.services.organization_service import OrganizationService

JSON_OBJECT = TypeAdapter(dict[str, object])


def create_organization(client: TestClient, slug: str) -> dict[str, object]:
    response = client.post(
        "/api/v1/organizations",
        json={
            "name": slug,
            "slug": slug,
            "country_code": "US",
            "default_currency": "USD",
            "timezone": "UTC",
        },
    )
    assert response.status_code == 201
    return JSON_OBJECT.validate_python(response.json())


def create_member(
    client: TestClient,
    organization_id: str,
    user_id: UUID,
    role: MembershipRole,
    membership_status: MembershipStatus = MembershipStatus.ACTIVE,
) -> dict[str, object]:
    response = client.post(
        f"/api/v1/organizations/{organization_id}/members",
        json={
            "user_id": str(user_id),
            "role": role.value,
            "status": membership_status.value,
        },
    )
    assert response.status_code == 201
    return JSON_OBJECT.validate_python(response.json())


def test_missing_identity_and_client_user_id_cannot_bypass_authentication(
    client: TestClient, identity: IdentityState
) -> None:
    organization = create_organization(client, "missing-identity")
    identity.user_id = None
    identity.is_platform_admin = False

    assert client.get(f"/api/v1/organizations/{organization['id']}").status_code == 401
    response = client.post(
        f"/api/v1/organizations/{organization['id']}/members",
        json={
            "user_id": str(uuid4()),
            "role": MembershipRole.ORGANIZATION_ADMIN.value,
            "status": MembershipStatus.ACTIVE.value,
        },
    )
    assert response.status_code == 401


def test_platform_admin_claim_manages_memberships_across_organizations(
    client: TestClient, identity: IdentityState
) -> None:
    first = create_organization(client, "platform-admin-first")
    second = create_organization(client, "platform-admin-second")
    assert identity.is_platform_admin is True

    for organization in (first, second):
        response = client.post(
            f"/api/v1/organizations/{organization['id']}/members",
            json={
                "user_id": str(uuid4()),
                "role": MembershipRole.VIEWER.value,
                "status": MembershipStatus.INVITED.value,
            },
        )
        assert response.status_code == 201


def test_platform_admin_membership_does_not_bypass_tenant_scope(
    client: TestClient, identity: IdentityState
) -> None:
    first = create_organization(client, "membership-platform-first")
    second = create_organization(client, "membership-platform-second")
    member_id = uuid4()
    create_member(
        client,
        str(first["id"]),
        member_id,
        MembershipRole.PLATFORM_ADMIN,
    )
    identity.user_id = member_id
    identity.is_platform_admin = False
    assert client.get(f"/api/v1/organizations/{first['id']}").status_code == 403
    assert client.get(f"/api/v1/organizations/{second['id']}").status_code == 403

    identity.is_platform_admin = True
    assert client.get(f"/api/v1/organizations/{second['id']}").status_code == 200


def test_nonmember_and_nonactive_members_are_forbidden(
    client: TestClient, identity: IdentityState
) -> None:
    organization = create_organization(client, "nonactive-members")
    organization_id = str(organization["id"])

    for membership_status in (
        MembershipStatus.INVITED,
        MembershipStatus.SUSPENDED,
        MembershipStatus.REVOKED,
    ):
        user_id = uuid4()
        create_member(
            client,
            organization_id,
            user_id,
            MembershipRole.VIEWER,
            membership_status,
        )
        identity.user_id = user_id
        identity.is_platform_admin = False
        response = client.get(f"/api/v1/organizations/{organization_id}/members")
        assert response.status_code == 403
        identity.is_platform_admin = True

    identity.user_id = uuid4()
    identity.is_platform_admin = False
    assert client.get(f"/api/v1/organizations/{organization_id}").status_code == 403


def test_viewer_reads_but_cannot_modify_memberships(
    client: TestClient, identity: IdentityState
) -> None:
    organization = create_organization(client, "viewer-permissions")
    organization_id = str(organization["id"])
    viewer_id = uuid4()
    membership = create_member(
        client,
        organization_id,
        viewer_id,
        MembershipRole.VIEWER,
    )
    identity.user_id = viewer_id
    identity.is_platform_admin = False

    assert client.get(f"/api/v1/organizations/{organization_id}/members").status_code == 200
    assert (
        client.get(
            f"/api/v1/organizations/{organization_id}/members/{membership['id']}"
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"/api/v1/organizations/{organization_id}/members/{membership['id']}/role",
            json={"role": MembershipRole.ANALYST.value},
        ).status_code
        == 403
    )


def test_organization_admin_manages_members_and_last_admin_is_protected(
    client: TestClient, identity: IdentityState
) -> None:
    organization = create_organization(client, "admin-permissions")
    organization_id = str(organization["id"])
    admin_id = uuid4()
    admin = create_member(
        client,
        organization_id,
        admin_id,
        MembershipRole.ORGANIZATION_ADMIN,
    )
    identity.user_id = admin_id
    identity.is_platform_admin = False

    invited = client.post(
        f"/api/v1/organizations/{organization_id}/members",
        json={"user_id": str(uuid4()), "role": MembershipRole.ANALYST.value},
    )
    assert invited.status_code == 201
    membership_id = invited.json()["id"]
    filtered = client.get(
        f"/api/v1/organizations/{organization_id}/members",
        params={
            "role": MembershipRole.ANALYST.value,
            "status": MembershipStatus.INVITED.value,
            "limit": 10,
        },
    )
    assert filtered.status_code == 200
    assert [item["id"] for item in filtered.json()] == [membership_id]
    assert (
        client.post(
            f"/api/v1/organizations/{organization_id}/members/{membership_id}/activate"
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/organizations/{organization_id}/members/{membership_id}/suspend"
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/organizations/{organization_id}/members/{membership_id}/revoke"
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/organizations/{organization_id}/members/{admin['id']}/suspend"
        ).status_code
        == 409
    )


def test_duplicate_and_cross_organization_membership_ids(
    client: TestClient, identity: IdentityState
) -> None:
    first = create_organization(client, "cross-membership-first")
    second = create_organization(client, "cross-membership-second")
    user_id = uuid4()
    first_admin = create_member(
        client,
        str(first["id"]),
        user_id,
        MembershipRole.ORGANIZATION_ADMIN,
    )
    second_admin = create_member(
        client,
        str(second["id"]),
        user_id,
        MembershipRole.ORGANIZATION_ADMIN,
    )
    duplicate = client.post(
        f"/api/v1/organizations/{first['id']}/members",
        json={
            "user_id": str(user_id),
            "role": MembershipRole.VIEWER.value,
        },
    )
    assert duplicate.status_code == 409

    identity.user_id = user_id
    identity.is_platform_admin = False
    hidden = client.get(f"/api/v1/organizations/{first['id']}/members/{second_admin['id']}")
    assert hidden.status_code == 404
    assert (
        client.get(f"/api/v1/organizations/{first['id']}/members/{first_admin['id']}").status_code
        == 200
    )


def test_existing_tenant_endpoints_enforce_authenticated_membership(
    client: TestClient, identity: IdentityState, db: Session
) -> None:
    organization_service = OrganizationService()
    membership_service = OrganizationMembershipService()
    finding_service = FindingService()
    first = organization_service.create(
        db,
        OrganizationCreate(
            name="Protected First",
            slug="protected-first",
            country_code="US",
            default_currency="USD",
            timezone="UTC",
        ),
    )
    second = organization_service.create(
        db,
        OrganizationCreate(
            name="Protected Second",
            slug="protected-second",
            country_code="US",
            default_currency="USD",
            timezone="UTC",
        ),
    )
    user_id = uuid4()
    membership_service.create(
        db,
        first.id,
        MembershipCreate(
            user_id=user_id,
            role=MembershipRole.VIEWER,
            status=MembershipStatus.ACTIVE,
        ),
        invited_by_user_id=uuid4(),
    )
    finding_service.create(
        db,
        first.id,
        FindingCreate(
            rule_id="AUTH-TEST",
            title="Authorized finding",
            summary="Organization A only",
            domain="maintenance",
            exposure_low=1,
            exposure_high=2,
            confidence_score=0.8,
            evidence=[
                {
                    "source_system": "test",
                    "source_record_id": "auth-1",
                    "evidence_type": "test",
                    "payload": {"ok": True},
                }
            ],
        ),
    )

    identity.user_id = user_id
    identity.is_platform_admin = False
    authorized = client.get(
        "/api/v1/command/findings",
        params={"organization_id": str(first.id)},
    )
    assert authorized.status_code == 200
    assert [item["title"] for item in authorized.json()] == ["Authorized finding"]
    assert (
        client.get(
            "/api/v1/command/findings",
            params={"organization_id": str(second.id)},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/recovery/actions",
            params={"organization_id": str(second.id)},
            json={
                "finding_id": str(uuid4()),
                "title": "Cross tenant",
                "owner": "nobody",
            },
        ).status_code
        == 403
    )
