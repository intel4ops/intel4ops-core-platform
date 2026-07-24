from uuid import UUID, uuid4

import pytest
from conftest import IdentityState
from fastapi.testclient import TestClient

from app.models.entities import MembershipRole, MembershipStatus


def create_organization(client: TestClient, slug: str) -> str:
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
    return str(response.json()["id"])


def create_membership(
    client: TestClient, organization_id: str, user_id: UUID, role: MembershipRole
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


def source_payload(code: str = "finance-erp") -> dict[str, object]:
    return {
        "name": "Finance ERP",
        "code": code,
        "system_type": "erp",
        "provider": "sap",
        "integration_method": "api",
        "environment": "production",
        "credential_reference": "vault://finance/erp",
        "configuration_metadata": {"region": "us"},
        "capabilities": ["invoices"],
    }


def test_admin_crud_filters_conflict_and_secret_response(
    client: TestClient, identity: IdentityState
) -> None:
    organization_id = create_organization(client, "source-api-admin")
    created = client.post(
        f"/api/v1/organizations/{organization_id}/source-systems",
        json=source_payload(),
    )
    assert created.status_code == 201
    body = created.json()
    assert "credential_reference" not in body
    source_id = body["id"]
    assert (
        client.post(
            f"/api/v1/organizations/{organization_id}/source-systems",
            json=source_payload(),
        ).status_code
        == 409
    )
    listed = client.get(
        f"/api/v1/organizations/{organization_id}/source-systems",
        params={"provider": "SAP", "system_type": "erp", "search": "finance"},
    )
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [source_id]
    updated = client.patch(
        f"/api/v1/organizations/{organization_id}/source-systems/{source_id}",
        json={"name": "Finance ERP Updated", "status": "configured"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "configured"


@pytest.mark.parametrize(
    ("role", "can_read", "can_operate", "can_admin"),
    [
        (MembershipRole.ORGANIZATION_ADMIN, True, True, True),
        (MembershipRole.OPERATOR, True, True, False),
        (MembershipRole.ANALYST, True, False, False),
        (MembershipRole.RECOVERY_MANAGER, True, False, False),
        (MembershipRole.VIEWER, True, False, False),
    ],
)
def test_role_matrix(
    client: TestClient,
    identity: IdentityState,
    role: MembershipRole,
    can_read: bool,
    can_operate: bool,
    can_admin: bool,
) -> None:
    identity.is_platform_admin = True
    role_slug = role.value.replace("_", "-")
    organization_id = create_organization(client, f"source-role-{role_slug}")
    source = client.post(
        f"/api/v1/organizations/{organization_id}/source-systems",
        json=source_payload(f"source-{role_slug}"),
    ).json()
    user_id = uuid4()
    create_membership(client, organization_id, user_id, role)
    identity.user_id = user_id
    identity.is_platform_admin = False

    read = client.get(f"/api/v1/organizations/{organization_id}/source-systems/{source['id']}")
    assert (read.status_code == 200) is can_read
    operated = client.post(
        f"/api/v1/organizations/{organization_id}/source-systems/{source['id']}/connection-failure"
    )
    assert (operated.status_code == 200) is can_operate
    changed = client.patch(
        f"/api/v1/organizations/{organization_id}/source-systems/{source['id']}",
        json={"description": "changed"},
    )
    assert (changed.status_code == 200) is can_admin


def test_cross_tenant_and_secret_metadata_are_rejected(
    client: TestClient, identity: IdentityState
) -> None:
    first = create_organization(client, "source-cross-first")
    second = create_organization(client, "source-cross-second")
    source_id = client.post(
        f"/api/v1/organizations/{first}/source-systems", json=source_payload()
    ).json()["id"]
    assert (
        client.get(f"/api/v1/organizations/{second}/source-systems/{source_id}").status_code == 404
    )
    unsafe = source_payload("unsafe")
    unsafe["configuration_metadata"] = {"nested": {"Client_Secret": "not-logged"}}
    response = client.post(f"/api/v1/organizations/{first}/source-systems", json=unsafe)
    assert response.status_code == 422
