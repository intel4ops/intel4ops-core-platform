from datetime import UTC, datetime
from uuid import uuid4

from conftest import IdentityState
from fastapi.testclient import TestClient

from app.models.entities import MembershipRole


def setup_context(client: TestClient, slug: str) -> tuple[str, str, str, str]:
    organization = client.post(
        "/api/v1/organizations",
        json={
            "name": slug,
            "slug": slug,
            "country_code": "US",
            "default_currency": "USD",
            "timezone": "UTC",
        },
    ).json()
    organization_id = organization["id"]
    source = client.post(
        f"/api/v1/organizations/{organization_id}/source-systems",
        json={
            "name": "ERP",
            "code": "erp",
            "system_type": "erp",
            "integration_method": "file_upload",
        },
    ).json()
    batch = client.post(
        f"/api/v1/organizations/{organization_id}/ingestion-batches",
        json={
            "source_system_id": source["id"],
            "batch_number": "batch-001",
            "ingestion_method": "file_upload",
            "trigger_type": "manual",
        },
    ).json()
    dataset = client.post(
        f"/api/v1/organizations/{organization_id}/datasets",
        json={
            "source_system_id": source["id"],
            "name": "Invoices",
            "code": "invoices",
            "domain": "invoices",
            "dataset_type": "transactional",
        },
    ).json()
    version = client.post(
        f"/api/v1/organizations/{organization_id}/datasets/{dataset['id']}/versions",
        json={
            "ingestion_batch_id": batch["id"],
            "source_file_name": "invoices.csv",
            "source_file_extension": "csv",
        },
    ).json()
    return organization_id, source["id"], batch["id"], version["id"]


def raw_payload(source_id: str, batch_id: str, version_id: str) -> dict[str, object]:
    return {
        "source_system_id": source_id,
        "ingestion_batch_id": batch_id,
        "dataset_version_id": version_id,
        "object_number": "raw-001",
        "object_type": "file",
        "storage_provider": "s3",
        "storage_reference": "s3://opaque/object",
        "original_filename": "invoices.csv",
        "file_extension": "csv",
        "media_type": "text/csv",
        "content_checksum_algorithm": "sha256",
        "content_checksum": "a" * 64,
        "size_bytes": 10,
        "received_at": datetime.now(UTC).isoformat(),
    }


def test_raw_api_flow_masks_storage_and_traverses_lineage(client: TestClient) -> None:
    organization_id, source_id, batch_id, version_id = setup_context(client, "raw-api-flow")
    created = client.post(
        f"/api/v1/organizations/{organization_id}/raw-storage-objects",
        json=raw_payload(source_id, batch_id, version_id),
    )
    assert created.status_code == 201
    body = created.json()
    assert "storage_reference" not in body
    assert "storage_container_reference" not in body
    raw_id = body["id"]

    client.post(
        f"/api/v1/organizations/{organization_id}/raw-storage-objects/{raw_id}/transition",
        json={"status": "received"},
    )
    client.post(
        f"/api/v1/organizations/{organization_id}/raw-storage-objects/{raw_id}/transition",
        json={"status": "verifying"},
    )
    verified = client.post(
        f"/api/v1/organizations/{organization_id}/raw-storage-objects/{raw_id}/verify-integrity",
        json={"checksum_algorithm": "sha256", "checksum": "a" * 64, "matched": True},
    )
    assert verified.status_code == 200
    assert (
        client.post(
            f"/api/v1/organizations/{organization_id}/raw-storage-objects/{raw_id}/seal"
        ).status_code
        == 200
    )
    node = client.get(
        f"/api/v1/organizations/{organization_id}/lineage/entities/raw_storage_object/{raw_id}"
    )
    graph = client.get(
        f"/api/v1/organizations/{organization_id}/lineage/nodes/{node.json()['id']}/upstream"
    )
    assert graph.status_code == 200
    assert len(graph.json()["nodes"]) == 5


def test_cross_tenant_hiding_secret_rejection_and_authorization(
    client: TestClient, identity: IdentityState
) -> None:
    organization_id, source_id, batch_id, version_id = setup_context(client, "raw-api-auth")
    other_id, _, _, _ = setup_context(client, "raw-api-auth-other")
    created = client.post(
        f"/api/v1/organizations/{organization_id}/raw-storage-objects",
        json=raw_payload(source_id, batch_id, version_id),
    )
    raw_id = created.json()["id"]
    assert (
        client.get(f"/api/v1/organizations/{other_id}/raw-storage-objects/{raw_id}").status_code
        == 404
    )
    unsafe = raw_payload(source_id, batch_id, version_id)
    unsafe["object_number"] = "unsafe"
    unsafe["storage_reference"] = "https://bucket/item?token=hidden"
    response = client.post(
        f"/api/v1/organizations/{organization_id}/raw-storage-objects", json=unsafe
    )
    assert response.status_code == 422
    assert "hidden" not in response.text

    viewer_id = uuid4()
    client.post(
        f"/api/v1/organizations/{organization_id}/members",
        json={
            "user_id": str(viewer_id),
            "role": MembershipRole.VIEWER.value,
            "status": "active",
        },
    )
    identity.user_id = viewer_id
    identity.is_platform_admin = False
    assert (
        client.get(
            f"/api/v1/organizations/{organization_id}/raw-storage-objects/{raw_id}"
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/organizations/{organization_id}/raw-storage-objects",
            json={
                **raw_payload(source_id, batch_id, version_id),
                "object_number": "viewer-write",
            },
        ).status_code
        == 403
    )
