from uuid import uuid4

from conftest import IdentityState
from fastapi.testclient import TestClient


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
    )
    assert organization.status_code == 201
    organization_id = organization.json()["id"]
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
    dataset = client.post(
        f"/api/v1/organizations/{organization_id}/datasets",
        json={
            "source_system_id": source.json()["id"],
            "name": "Invoices",
            "code": "invoices",
            "domain": "finance",
            "dataset_type": "transactional",
            "default_currency": "USD",
        },
    )
    assert dataset.status_code == 201
    dataset_id = dataset.json()["id"]
    assessment = client.post(
        f"/api/v1/organizations/{organization_id}/datasets/{dataset_id}/trust-assessments",
        json={
            "records": [{"id": "1", "amount": "10.25"}],
            "rule_configurations": {
                "required_field_completeness": {"required_fields": ["id", "amount"]},
                "numeric_range_validity": {"numeric_ranges": {"amount": {"minimum": 0}}},
            },
        },
    )
    assert assessment.status_code == 201
    return organization_id, dataset_id, assessment.json()["id"]


def test_intelligence_api_execution_registry_and_lookup(client: TestClient) -> None:
    organization_id, dataset_id, assessment_id = api_foundation(client, "intelligence-api")
    response = client.post(
        f"/api/v1/organizations/{organization_id}/intelligence-executions",
        json={
            "dataset_id": dataset_id,
            "trust_assessment_id": assessment_id,
            "execution_type": "calculation",
            "definition_code": "sum",
            "records": [{"amount": "0.10"}, {"amount": "0.20"}],
            "parameters": {"field": "amount"},
            "currency": "USD",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["result_value"] == "0.300000000000"
    assert body["status"] == "completed"

    fetched = client.get(
        f"/api/v1/organizations/{organization_id}/intelligence-executions/{body['id']}"
    )
    listed = client.get(f"/api/v1/organizations/{organization_id}/intelligence-executions")
    calculations = client.get(f"/api/v1/organizations/{organization_id}/calculation-definitions")
    rules = client.get(f"/api/v1/organizations/{organization_id}/rule-definitions")
    assert fetched.status_code == 200
    assert [item["id"] for item in listed.json()] == [body["id"]]
    assert any(item["code"] == "sum" for item in calculations.json())
    assert any(item["code"] == "threshold_exceeded" for item in rules.json())


def test_intelligence_api_authorization_and_safe_errors(
    client: TestClient, identity: IdentityState
) -> None:
    organization_id, dataset_id, assessment_id = api_foundation(client, "intelligence-auth")
    viewer_id = uuid4()
    membership = client.post(
        f"/api/v1/organizations/{organization_id}/members",
        json={"user_id": str(viewer_id), "role": "viewer", "status": "active"},
    )
    assert membership.status_code == 201
    identity.user_id = viewer_id
    identity.is_platform_admin = False

    execute = client.post(
        f"/api/v1/organizations/{organization_id}/intelligence-executions",
        json={
            "dataset_id": dataset_id,
            "trust_assessment_id": assessment_id,
            "execution_type": "calculation",
            "definition_code": "unknown_definition",
        },
    )
    definitions = client.get(f"/api/v1/organizations/{organization_id}/calculation-definitions")
    assert execute.status_code == 403
    assert definitions.status_code == 200
