from uuid import uuid4

from conftest import IdentityState
from fastapi.testclient import TestClient


def definition_payload(code: str, organization_id: str | None = None) -> dict[str, object]:
    return {
        "stable_code": code,
        "name": "API governed definition",
        "description": "Tenant-safe API test definition.",
        "knowledge_class": "kpi",
        "analytical_level": "arithmetic",
        "domain": "operations",
        "owner_organization_id": organization_id,
        "scope_type": "organization" if organization_id else "shared_core",
        "is_system_definition": organization_id is None,
    }


def version_payload() -> dict[str, object]:
    return {
        "semantic_version": "1.0.0",
        "quality_level": "provisional",
        "expression_schema": {
            "operation": "sum",
            "inputs": ["amount"],
            "parameters": {},
        },
        "output_type": "currency",
        "output_unit": "USD",
        "currency_code": "USD",
        "trust_requirement": {"minimum_status": "completed"},
        "readiness_requirement": {"analytical_level": "arithmetic"},
        "input_requirements": [
            {
                "input_code": "amount",
                "canonical_entity": "transaction",
                "canonical_field": "amount",
                "expected_type": "currency",
                "expected_unit": "USD",
                "currency_code": "USD",
            }
        ],
        "evidence_requirements": [
            {
                "evidence_type": "calculation_trace",
                "requirement_code": "CALCULATION_TRACE",
                "description": "Bounded trace.",
                "retention_class": "governed_reference",
            }
        ],
    }


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


def test_oikb_api_crud_version_errors_and_resolution(
    client: TestClient, identity: IdentityState
) -> None:
    organization_id = create_organization(client, "oikb-api")
    created = client.post(
        "/api/v1/oikb/definitions",
        json=definition_payload("SHARED.OPERATIONS.API_TEST", organization_id),
    )
    assert created.status_code == 201
    definition_id = created.json()["id"]
    duplicate = client.post(
        "/api/v1/oikb/definitions",
        json=definition_payload("SHARED.OPERATIONS.API_TEST", organization_id),
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "OIKB_CONFLICT"
    version = client.post(
        f"/api/v1/oikb/definitions/{definition_id}/versions",
        params={"organization_id": organization_id},
        json=version_payload(),
    )
    assert version.status_code == 201
    version_id = version.json()["id"]
    listed = client.get(
        "/api/v1/oikb/definitions",
        params={"organization_id": organization_id, "page": 1, "page_size": 10},
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert (
        client.get(
            f"/api/v1/oikb/versions/{version_id}/execution-package",
            params={"organization_id": organization_id},
        ).status_code
        == 409
    )
    unresolved = client.post(
        "/api/v1/oikb/resolve",
        json={
            "organization_id": organization_id,
            "stable_code": "SHARED.OPERATIONS.API_TEST",
        },
    )
    assert unresolved.status_code == 200
    assert unresolved.json()["status"] == "unresolved"
    assert identity.is_platform_admin


def test_oikb_api_rejects_cross_tenant_private_definition(
    client: TestClient, identity: IdentityState
) -> None:
    first = create_organization(client, "oikb-first")
    second = create_organization(client, "oikb-second")
    created = client.post(
        "/api/v1/oikb/definitions",
        json=definition_payload("SHARED.OPERATIONS.PRIVATE_TEST", first),
    )
    assert created.status_code == 201
    definition_id = created.json()["id"]
    identity.is_platform_admin = False
    identity.user_id = uuid4()
    denied = client.get(
        f"/api/v1/oikb/definitions/{definition_id}",
        params={"organization_id": second},
    )
    assert denied.status_code == 403
