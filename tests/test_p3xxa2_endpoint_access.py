from io import BytesIO
from uuid import uuid4

from conftest import IdentityState
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

from app.models.entities import MembershipRole, MembershipStatus

MAINTENANCE_CSV = b"asset_id,failure_code,downtime_hours,repair_cost\nBUS-1,BRAKE,4,200\n"
JSON_OBJECT = TypeAdapter(dict[str, object])


def _create_organization(client: TestClient, slug: str) -> dict[str, object]:
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


def _add_member(
    client: TestClient, organization_id: str, user_id: object, role: MembershipRole
) -> None:
    response = client.post(
        f"/api/v1/organizations/{organization_id}/members",
        json={
            "user_id": str(user_id),
            "role": role.value,
            "status": MembershipStatus.ACTIVE.value,
        },
    )
    assert response.status_code == 201


# ---------------------------------------------------------------------------
# GET /api/v1/health -- public, no dependency
# ---------------------------------------------------------------------------


def test_health_remains_callable(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_callable_without_any_authorization_header(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={})
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# POST /api/v1/trust/profile -- public, no dependency
# ---------------------------------------------------------------------------


def test_trust_profile_callable_without_authentication(client: TestClient) -> None:
    response = client.post(
        "/api/v1/trust/profile",
        files={"file": ("assets.csv", BytesIO(b"asset_id\nBUS-1\nBUS-2\n"), "text/csv")},
    )
    assert response.status_code == 200
    assert response.json()["row_count"] == 2


# ---------------------------------------------------------------------------
# GET/POST /api/v1/organizations -- platform-admin only
# ---------------------------------------------------------------------------


def test_platform_admin_can_list_and_create_organizations(client: TestClient) -> None:
    assert client.get("/api/v1/organizations").status_code == 200
    created = client.post(
        "/api/v1/organizations",
        json={
            "name": "allowed-org",
            "slug": "allowed-org",
            "country_code": "US",
            "default_currency": "USD",
            "timezone": "UTC",
        },
    )
    assert created.status_code == 201


def test_non_platform_admin_cannot_list_or_create_organizations(
    client: TestClient, identity: IdentityState
) -> None:
    identity.is_platform_admin = False
    assert client.get("/api/v1/organizations").status_code == 403
    response = client.post(
        "/api/v1/organizations",
        json={
            "name": "denied-org",
            "slug": "denied-org",
            "country_code": "US",
            "default_currency": "USD",
            "timezone": "UTC",
        },
    )
    assert response.status_code == 403


def test_unauthenticated_identity_cannot_list_or_create_organizations(
    client: TestClient, identity: IdentityState
) -> None:
    identity.user_id = None
    assert client.get("/api/v1/organizations").status_code == 401


# ---------------------------------------------------------------------------
# POST /api/v1/intelligence/maintenance/analyze -- org role required
# ---------------------------------------------------------------------------


def test_authorized_org_role_can_execute_maintenance_analyze(
    client: TestClient, identity: IdentityState
) -> None:
    organization = _create_organization(client, "maint-authorized")
    analyst_id = uuid4()
    _add_member(client, str(organization["id"]), analyst_id, MembershipRole.ANALYST)

    identity.user_id = analyst_id
    identity.is_platform_admin = False
    response = client.post(
        "/api/v1/intelligence/maintenance/analyze",
        params={"organization_id": organization["id"]},
        files={"file": ("failures.csv", BytesIO(MAINTENANCE_CSV), "text/csv")},
    )
    assert response.status_code == 200


def test_unauthorized_identity_cannot_execute_maintenance_analyze(
    client: TestClient, identity: IdentityState
) -> None:
    organization = _create_organization(client, "maint-unauthorized")

    identity.user_id = uuid4()
    identity.is_platform_admin = False
    response = client.post(
        "/api/v1/intelligence/maintenance/analyze",
        params={"organization_id": organization["id"]},
        files={"file": ("failures.csv", BytesIO(MAINTENANCE_CSV), "text/csv")},
    )
    assert response.status_code == 403


def test_viewer_role_cannot_execute_maintenance_analyze(
    client: TestClient, identity: IdentityState
) -> None:
    organization = _create_organization(client, "maint-viewer-denied")
    viewer_id = uuid4()
    _add_member(client, str(organization["id"]), viewer_id, MembershipRole.VIEWER)

    identity.user_id = viewer_id
    identity.is_platform_admin = False
    response = client.post(
        "/api/v1/intelligence/maintenance/analyze",
        params={"organization_id": organization["id"]},
        files={"file": ("failures.csv", BytesIO(MAINTENANCE_CSV), "text/csv")},
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# GET /api/v1/command/findings -- org role required
# ---------------------------------------------------------------------------


def test_authorized_org_role_can_list_findings(client: TestClient, identity: IdentityState) -> None:
    organization = _create_organization(client, "findings-authorized")
    viewer_id = uuid4()
    _add_member(client, str(organization["id"]), viewer_id, MembershipRole.VIEWER)

    identity.user_id = viewer_id
    identity.is_platform_admin = False
    response = client.get(
        "/api/v1/command/findings", params={"organization_id": organization["id"]}
    )
    assert response.status_code == 200
    assert response.json() == []


def test_unauthorized_identity_cannot_list_findings(
    client: TestClient, identity: IdentityState
) -> None:
    organization = _create_organization(client, "findings-unauthorized")

    identity.user_id = uuid4()
    identity.is_platform_admin = False
    response = client.get(
        "/api/v1/command/findings", params={"organization_id": organization["id"]}
    )
    assert response.status_code == 403
