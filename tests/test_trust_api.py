from uuid import UUID, uuid4

from conftest import IdentityState
from fastapi.testclient import TestClient

from app.models.entities import MembershipRole


def api_foundation(client: TestClient, slug: str) -> tuple[str, str, str]:
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
            "name": "Source",
            "code": "source",
            "system_type": "erp",
            "integration_method": "api",
        },
    ).json()
    batch = client.post(
        f"/api/v1/organizations/{organization_id}/ingestion-batches",
        json={
            "source_system_id": source["id"],
            "batch_number": "batch-001",
            "ingestion_method": "api",
            "trigger_type": "manual",
        },
    ).json()
    dataset = client.post(
        f"/api/v1/organizations/{organization_id}/datasets",
        json={
            "source_system_id": source["id"],
            "name": "Shared records",
            "code": "shared-records",
            "domain": "operations",
            "dataset_type": "transactional",
        },
    ).json()
    return organization_id, batch["id"], dataset["id"]


def api_payload(batch_id: str | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "evaluation_time": "2026-07-24T12:00:00Z",
        "records": [
            {"id": "1", "amount": 10, "source_id": "S1"},
            {"id": "2", "amount": None, "source_id": "S2"},
        ],
        "rule_configurations": {
            "required_field_completeness": {
                "required_fields": ["id", "amount"],
                "identifier_field": "id",
            },
            "primary_identifier_uniqueness": {"identifier_field": "id"},
            "lineage_completeness": {
                "lineage_fields": ["source_id"],
                "identifier_field": "id",
            },
        },
    }
    if batch_id is not None:
        payload["ingestion_batch_id"] = batch_id
    return payload


def add_member(
    client: TestClient,
    organization_id: str,
    user_id: UUID,
    role: MembershipRole,
) -> None:
    response = client.post(
        f"/api/v1/organizations/{organization_id}/members",
        json={"user_id": str(user_id), "role": role.value, "status": "active"},
    )
    assert response.status_code == 201


def test_all_trust_endpoints_and_bounded_evidence(client: TestClient) -> None:
    organization_id, batch_id, dataset_id = api_foundation(client, "trust-api")
    created = client.post(
        f"/api/v1/organizations/{organization_id}/datasets/{dataset_id}/trust-assessments",
        json=api_payload(batch_id),
    )
    assert created.status_code == 201
    assessment_id = created.json()["id"]
    assert created.json()["overall_score"] is not None

    summary = client.get(
        f"/api/v1/organizations/{organization_id}/trust-assessments/{assessment_id}"
    )
    assert summary.status_code == 200
    rules = client.get(
        f"/api/v1/organizations/{organization_id}/trust-assessments/{assessment_id}/rules"
    )
    assert rules.status_code == 200
    assert len(rules.json()) == 3
    evidence = client.get(
        f"/api/v1/organizations/{organization_id}/trust-assessments/"
        f"{assessment_id}/evidence?limit=1"
    )
    assert evidence.status_code == 200
    assert evidence.json()["limit"] == 1
    assert evidence.json()["returned"] <= 1
    readiness = client.get(
        f"/api/v1/organizations/{organization_id}/trust-assessments/{assessment_id}/readiness"
    )
    assert readiness.status_code == 200
    assert len(readiness.json()) == 5
    latest = client.get(
        f"/api/v1/organizations/{organization_id}/datasets/{dataset_id}/latest-trust-assessment"
    )
    assert latest.status_code == 200
    assert latest.json()["id"] == assessment_id


def test_trust_api_tenant_isolation_and_role_authorization(
    client: TestClient, identity: IdentityState
) -> None:
    first_id, _, first_dataset = api_foundation(client, "trust-api-first")
    second_id, _, _ = api_foundation(client, "trust-api-second")
    assessment = client.post(
        f"/api/v1/organizations/{first_id}/datasets/{first_dataset}/trust-assessments",
        json=api_payload(),
    ).json()
    assessment_id = assessment["id"]
    assert (
        client.post(
            f"/api/v1/organizations/{second_id}/datasets/{first_dataset}/trust-assessments",
            json=api_payload(),
        ).status_code
        == 404
    )
    for suffix in ("", "/rules", "/evidence", "/readiness"):
        assert (
            client.get(
                f"/api/v1/organizations/{second_id}/trust-assessments/{assessment_id}{suffix}"
            ).status_code
            == 404
        )

    viewer_id = uuid4()
    add_member(client, first_id, viewer_id, MembershipRole.VIEWER)
    identity.user_id = viewer_id
    identity.is_platform_admin = False
    assert (
        client.get(
            f"/api/v1/organizations/{first_id}/trust-assessments/{assessment_id}"
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/organizations/{first_id}/datasets/{first_dataset}/trust-assessments",
            json=api_payload(),
        ).status_code
        == 403
    )
