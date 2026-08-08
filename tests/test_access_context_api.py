from uuid import UUID, uuid4

from conftest import IdentityState
from fastapi.testclient import TestClient
from pydantic import TypeAdapter
from sqlalchemy.orm import Session

from app.models.entities import MembershipRole, MembershipStatus
from app.schemas.memberships import MembershipCreate
from app.services.membership_service import OrganizationMembershipService
from app.services.organization_service import OrganizationService

JSON_OBJECT = TypeAdapter(dict[str, object])


def create_organization_self_service(client: TestClient, slug: str) -> dict[str, object]:
    response = client.post(
        "/api/v1/me/organizations",
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
    user_id: object,
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


def test_platform_admin_route_is_unaffected_by_self_service_route(
    client: TestClient, identity: IdentityState
) -> None:
    response = client.post(
        "/api/v1/organizations",
        json={
            "name": "admin-provisioned",
            "slug": "admin-provisioned",
            "country_code": "US",
            "default_currency": "USD",
            "timezone": "UTC",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["slug"] == "admin-provisioned"
    organization_id = body["id"]
    members = client.get(f"/api/v1/organizations/{organization_id}/members")
    assert members.status_code == 200
    assert members.json() == []


def test_self_service_organization_creation_grants_active_owner_membership(
    client: TestClient, identity: IdentityState
) -> None:
    identity.is_platform_admin = False
    organization = create_organization_self_service(client, "self-service-owner")

    identity_response = client.get("/api/v1/me")
    assert identity_response.status_code == 200
    body = identity_response.json()
    assert body["user_id"] == str(identity.user_id)
    assert len(body["memberships"]) == 1
    membership = body["memberships"][0]
    assert membership["organization"]["id"] == organization["id"]
    assert membership["role"] == MembershipRole.ORGANIZATION_ADMIN.value
    assert membership["status"] == MembershipStatus.ACTIVE.value


def test_self_service_organization_creation_rejects_duplicate_slug(
    client: TestClient, identity: IdentityState
) -> None:
    create_organization_self_service(client, "self-service-duplicate")
    identity.user_id = uuid4()
    response = client.post(
        "/api/v1/me/organizations",
        json={
            "name": "self-service-duplicate",
            "slug": "self-service-duplicate",
            "country_code": "US",
            "default_currency": "USD",
            "timezone": "UTC",
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "organization_conflict"


def test_self_service_organization_creation_requires_authentication(
    client: TestClient, identity: IdentityState
) -> None:
    identity.user_id = None
    response = client.post(
        "/api/v1/me/organizations",
        json={
            "name": "unauthenticated",
            "slug": "unauthenticated",
            "country_code": "US",
            "default_currency": "USD",
            "timezone": "UTC",
        },
    )
    assert response.status_code == 401


def test_invitation_lifecycle_via_api(client: TestClient, identity: IdentityState) -> None:
    identity.is_platform_admin = False
    organization = create_organization_self_service(client, "invitation-lifecycle")
    organization_id = organization["id"]

    created = client.post(
        f"/api/v1/organizations/{organization_id}/invitations",
        json={"email": "invitee@example.com", "role": MembershipRole.ANALYST.value},
    )
    assert created.status_code == 201
    created_body = created.json()
    token = created_body["token"]
    assert len(token) >= 32
    invitation_id = created_body["invitation"]["id"]
    assert created_body["invitation"]["status"] == "pending"

    listed = client.get(f"/api/v1/organizations/{organization_id}/invitations")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [invitation_id]

    invitee_id = uuid4()
    identity.user_id = invitee_id
    accepted = client.post("/api/v1/invitations/accept", json={"token": token})
    assert accepted.status_code == 200
    membership = accepted.json()
    assert membership["role"] == MembershipRole.ANALYST.value
    assert membership["status"] == MembershipStatus.ACTIVE.value
    assert membership["organization_id"] == organization_id

    identity.user_id = uuid4()
    identity.is_platform_admin = True
    second_invite = client.post(
        f"/api/v1/organizations/{organization_id}/invitations",
        json={"email": "second@example.com", "role": MembershipRole.VIEWER.value},
    )
    assert second_invite.status_code == 201
    second_invitation_id = second_invite.json()["invitation"]["id"]
    revoked = client.post(
        f"/api/v1/organizations/{organization_id}/invitations/{second_invitation_id}/revoke"
    )
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"


def test_invitation_creation_requires_organization_admin_role(
    client: TestClient, identity: IdentityState
) -> None:
    identity.is_platform_admin = False
    organization = create_organization_self_service(client, "invitation-role-gate")
    organization_id = str(organization["id"])

    viewer_id = uuid4()
    create_member(client, organization_id, viewer_id, MembershipRole.VIEWER)
    identity.user_id = viewer_id

    response = client.post(
        f"/api/v1/organizations/{organization_id}/invitations",
        json={"email": "blocked@example.com", "role": MembershipRole.VIEWER.value},
    )
    assert response.status_code == 403


def test_invitation_accept_requires_authentication(
    client: TestClient, identity: IdentityState
) -> None:
    identity.user_id = None
    response = client.post("/api/v1/invitations/accept", json={"token": "x" * 32})
    assert response.status_code == 401


def test_invitation_accept_ignores_role_supplied_by_caller(
    client: TestClient, identity: IdentityState
) -> None:
    identity.is_platform_admin = False
    organization = create_organization_self_service(client, "invitation-no-self-escalation")
    organization_id = str(organization["id"])

    created = client.post(
        f"/api/v1/organizations/{organization_id}/invitations",
        json={"email": "escalation@example.com", "role": MembershipRole.VIEWER.value},
    )
    assert created.status_code == 201
    token = created.json()["token"]

    identity.user_id = uuid4()
    accepted = client.post(
        "/api/v1/invitations/accept",
        json={"token": token, "role": MembershipRole.ORGANIZATION_ADMIN.value},
    )
    assert accepted.status_code == 200
    assert accepted.json()["role"] == MembershipRole.VIEWER.value


def test_access_context_states(client: TestClient, identity: IdentityState, db: Session) -> None:
    identity.is_platform_admin = False
    no_membership = client.get("/api/v1/me/context")
    assert no_membership.status_code == 200
    assert no_membership.json()["state"] == "no_membership"

    organization = create_organization_self_service(client, "access-context-states")
    organization_id = str(organization["id"])

    active = client.get("/api/v1/me/context")
    assert active.status_code == 200
    active_body = active.json()
    assert active_body["state"] == "active"
    assert active_body["role"] == MembershipRole.ORGANIZATION_ADMIN.value
    assert "invite_members" in active_body["permitted_actions"]

    second_organization = create_organization_self_service(client, "access-context-second")
    second_organization_id = UUID(str(second_organization["id"]))
    membership_service = OrganizationMembershipService()
    organization_service = OrganizationService()
    membership_service.activate(
        db,
        second_organization_id,
        membership_service.list(db, second_organization_id)[0].id,
    )
    ambiguous = client.get("/api/v1/me/context")
    assert ambiguous.status_code == 200
    assert ambiguous.json()["state"] == "multiple_organizations"

    scoped = client.get("/api/v1/me/context", params={"organization_id": organization_id})
    assert scoped.status_code == 200
    assert scoped.json()["state"] == "active"

    organization_service.deactivate(db, UUID(organization_id))
    suspended_org = client.get("/api/v1/me/context", params={"organization_id": organization_id})
    assert suspended_org.status_code == 200
    assert suspended_org.json()["state"] == "suspended_organization"

    stranger_id = uuid4()
    identity.user_id = stranger_id
    unknown = client.get(
        "/api/v1/me/context", params={"organization_id": second_organization["id"]}
    )
    assert unknown.status_code == 200
    assert unknown.json()["state"] == "no_membership"

    pending_org = create_organization_self_service(client, "access-context-pending")
    pending_org_id = UUID(str(pending_org["id"]))
    invited_id = uuid4()
    membership_service.create(
        db,
        pending_org_id,
        MembershipCreate(user_id=invited_id, role=MembershipRole.VIEWER),
        invited_by_user_id=uuid4(),
    )
    identity.user_id = invited_id
    pending = client.get("/api/v1/me/context", params={"organization_id": pending_org["id"]})
    assert pending.status_code == 200
    assert pending.json()["state"] == "pending_invitation"

    revoked_id = uuid4()
    membership_service.create(
        db,
        pending_org_id,
        MembershipCreate(
            user_id=revoked_id, role=MembershipRole.VIEWER, status=MembershipStatus.REVOKED
        ),
        invited_by_user_id=uuid4(),
    )
    identity.user_id = revoked_id
    revoked = client.get("/api/v1/me/context", params={"organization_id": pending_org["id"]})
    assert revoked.status_code == 200
    assert revoked.json()["state"] == "revoked_membership"


def test_access_summary_requires_organization_read_role(
    client: TestClient, identity: IdentityState
) -> None:
    identity.is_platform_admin = False
    organization = create_organization_self_service(client, "access-summary-gate")
    organization_id = organization["id"]

    owner_view = client.get(f"/api/v1/organizations/{organization_id}/access-summary")
    assert owner_view.status_code == 200
    body = owner_view.json()
    assert body["organization_id"] == organization_id
    assert body["organization_status"] == "active"
    assert body["enabled_entitlements"] == []
    assert body["industry_pack_codes"] == []

    identity.user_id = uuid4()
    forbidden = client.get(f"/api/v1/organizations/{organization_id}/access-summary")
    assert forbidden.status_code == 403
