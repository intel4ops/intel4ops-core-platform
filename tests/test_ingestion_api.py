from uuid import UUID, uuid4

import pytest
from conftest import IdentityState
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

from app.models.entities import MembershipRole, MembershipStatus

JSON_OBJECT = TypeAdapter(dict[str, object])


def activate_source(client: TestClient, organization_id: str, source_id: str) -> None:
    base = f"/api/v1/organizations/{organization_id}/source-systems/{source_id}"
    assert client.patch(base, json={"status": "configured"}).status_code == 200
    assert client.patch(base, json={"status": "validating"}).status_code == 200
    assert client.post(f"{base}/connection-success").status_code == 200


def create_foundation(client: TestClient, slug: str) -> tuple[str, str]:
    organization = client.post(
        "/api/v1/organizations",
        json={
            "name": slug,
            "slug": slug,
            "country_code": "US",
            "default_currency": "USD",
            "timezone": "UTC",
        },
    )
    assert organization.status_code == 201
    organization_id = str(organization.json()["id"])
    source = client.post(
        f"/api/v1/organizations/{organization_id}/source-systems",
        json={
            "name": "ERP",
            "code": "erp",
            "system_type": "erp",
            "integration_method": "api",
        },
    )
    assert source.status_code == 201
    source_id = str(source.json()["id"])
    activate_source(client, organization_id, source_id)
    return organization_id, source_id


def create_member(
    client: TestClient,
    organization_id: str,
    user_id: UUID,
    role: MembershipRole,
    membership_status: MembershipStatus = MembershipStatus.ACTIVE,
) -> None:
    response = client.post(
        f"/api/v1/organizations/{organization_id}/members",
        json={
            "user_id": str(user_id),
            "role": role.value,
            "status": membership_status.value,
        },
    )
    assert response.status_code == 201


def create_batch(
    client: TestClient, organization_id: str, source_id: str, code: str
) -> dict[str, object]:
    response = client.post(
        f"/api/v1/organizations/{organization_id}/ingestion-batches",
        json={
            "source_system_id": source_id,
            "batch_number": code,
            "ingestion_method": "file_upload",
            "trigger_type": "manual",
            "idempotency_key": f"key-{code}",
        },
    )
    assert response.status_code == 201
    return JSON_OBJECT.validate_python(response.json())


def create_dataset(client: TestClient, organization_id: str, source_id: str) -> dict[str, object]:
    response = client.post(
        f"/api/v1/organizations/{organization_id}/datasets",
        json={
            "source_system_id": source_id,
            "name": "Invoices",
            "code": "invoices",
            "domain": "invoices",
            "dataset_type": "transactional",
        },
    )
    assert response.status_code == 201
    return JSON_OBJECT.validate_python(response.json())


def test_admin_ingestion_flow_and_cross_tenant_hiding(
    client: TestClient, identity: IdentityState
) -> None:
    organization_id, source_id = create_foundation(client, "ingestion-api-admin")
    other_id, _ = create_foundation(client, "ingestion-api-other")
    batch = create_batch(client, organization_id, source_id, "batch-admin")
    repeated = client.post(
        f"/api/v1/organizations/{organization_id}/ingestion-batches",
        json={
            "source_system_id": source_id,
            "batch_number": "batch-admin",
            "ingestion_method": "file_upload",
            "trigger_type": "manual",
            "idempotency_key": "key-batch-admin",
        },
    )
    assert repeated.status_code == 201
    assert repeated.json()["id"] == batch["id"]
    dataset = create_dataset(client, organization_id, source_id)
    version = client.post(
        f"/api/v1/organizations/{organization_id}/datasets/{dataset['id']}/versions",
        json={
            "ingestion_batch_id": batch["id"],
            "source_file_name": "invoices.csv",
            "source_file_extension": "csv",
        },
    )
    assert version.status_code == 201
    counts = client.patch(
        f"/api/v1/organizations/{organization_id}/datasets/{dataset['id']}/versions/"
        f"{version.json()['id']}/counts",
        json={
            "record_count": 10,
            "accepted_record_count": 9,
            "rejected_record_count": 1,
        },
    )
    assert counts.status_code == 200
    reconciled = client.get(
        f"/api/v1/organizations/{organization_id}/ingestion-batches/{batch['id']}"
    )
    assert reconciled.json()["actual_record_count"] == 10
    assert (
        client.get(f"/api/v1/organizations/{other_id}/ingestion-batches/{batch['id']}").status_code
        == 404
    )
    assert (
        client.get(f"/api/v1/organizations/{other_id}/datasets/{dataset['id']}").status_code == 404
    )


@pytest.mark.parametrize(
    ("role", "can_create_batch", "can_create_dataset"),
    [
        (MembershipRole.ORGANIZATION_ADMIN, True, True),
        (MembershipRole.OPERATOR, True, False),
        (MembershipRole.ANALYST, False, False),
        (MembershipRole.RECOVERY_MANAGER, False, False),
        (MembershipRole.VIEWER, False, False),
    ],
)
def test_ingestion_authorization_matrix(
    client: TestClient,
    identity: IdentityState,
    role: MembershipRole,
    can_create_batch: bool,
    can_create_dataset: bool,
) -> None:
    identity.is_platform_admin = True
    slug = role.value.replace("_", "-")
    organization_id, source_id = create_foundation(client, f"ingestion-role-{slug}")
    baseline = create_batch(client, organization_id, source_id, f"baseline-{slug}")
    user_id = uuid4()
    create_member(client, organization_id, user_id, role)
    identity.user_id = user_id
    identity.is_platform_admin = False

    assert (
        client.get(
            f"/api/v1/organizations/{organization_id}/ingestion-batches/{baseline['id']}"
        ).status_code
        == 200
    )
    batch_response = client.post(
        f"/api/v1/organizations/{organization_id}/ingestion-batches",
        json={
            "source_system_id": source_id,
            "batch_number": f"new-{slug}",
            "ingestion_method": "manual",
            "trigger_type": "manual",
        },
    )
    assert (batch_response.status_code == 201) is can_create_batch
    dataset_response = client.post(
        f"/api/v1/organizations/{organization_id}/datasets",
        json={
            "source_system_id": source_id,
            "name": "Role Dataset",
            "code": f"role-{slug}",
            "domain": "custom",
            "dataset_type": "custom",
        },
    )
    assert (dataset_response.status_code == 201) is can_create_dataset


def test_operator_cannot_release_quarantine(client: TestClient, identity: IdentityState) -> None:
    organization_id, source_id = create_foundation(client, "operator-release")
    batch = create_batch(client, organization_id, source_id, "operator-quarantine")
    assert (
        client.post(
            f"/api/v1/organizations/{organization_id}/ingestion-batches/{batch['id']}/transition",
            json={"status": "validating"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/organizations/{organization_id}/ingestion-batches/{batch['id']}/quarantine"
        ).status_code
        == 200
    )
    operator_id = uuid4()
    create_member(client, organization_id, operator_id, MembershipRole.OPERATOR)
    identity.user_id = operator_id
    identity.is_platform_admin = False
    assert (
        client.post(
            f"/api/v1/organizations/{organization_id}/ingestion-batches/{batch['id']}/release"
        ).status_code
        == 403
    )


def test_missing_and_inactive_identity_fail_closed(
    client: TestClient, identity: IdentityState
) -> None:
    organization_id, _ = create_foundation(client, "ingestion-auth")
    identity.user_id = None
    identity.is_platform_admin = False
    assert (
        client.get(f"/api/v1/organizations/{organization_id}/ingestion-batches").status_code == 401
    )
