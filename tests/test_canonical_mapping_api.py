from uuid import uuid4

from conftest import IdentityState
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.schemas.contracts import OrganizationCreate
from app.services.organization_service import OrganizationService


def test_catalog_and_tenant_api_authorization(
    client: TestClient,
    db: Session,
    identity: IdentityState,
) -> None:
    created = client.post(
        "/api/v1/canonical-mapping/canonical-types?kind=entity",
        json={
            "type_code": "customer_api",
            "display_name": "Customer",
            "scope_type": "shared_core",
            "scope_key": "shared_core",
            "identity_strategy_code": "exact_identifier",
        },
    )
    assert created.status_code == 201
    entity_type_id = created.json()["id"]

    organization = OrganizationService().create(
        db,
        OrganizationCreate(
            name="Canonical API",
            slug="canonical-api",
            country_code="US",
            default_currency="USD",
            timezone="UTC",
        ),
    )
    listed = client.get(
        f"/api/v1/organizations/{organization.id}/canonical-mapping/canonical-types?kind=entity"
    )
    assert listed.status_code == 200
    assert {item["type_code"] for item in listed.json()} == {"customer_api"}

    mismatched = client.post(
        f"/api/v1/organizations/{organization.id}/canonical-mapping/mapping-templates",
        json={
            "template_code": "wrong_owner",
            "name": "Wrong owner",
            "scope_type": "organization",
            "scope_key": f"organization:{organization.id}",
            "owner_organization_id": str(uuid4()),
            "target_canonical_type_kind": "entity",
            "target_canonical_type_id": entity_type_id,
        },
    )
    assert mismatched.status_code == 403
    assert mismatched.json()["detail"]["code"] == "TEMPLATE_SCOPE_MISMATCH"

    identity.user_id = None
    denied = client.get(
        f"/api/v1/organizations/{organization.id}/canonical-mapping/canonical-types?kind=entity"
    )
    assert denied.status_code == 401


def test_validation_rejects_unsafe_canonical_codes(client: TestClient) -> None:
    response = client.post(
        "/api/v1/canonical-mapping/canonical-types?kind=entity",
        json={
            "type_code": "../Customer",
            "display_name": "Customer",
            "scope_type": "shared_core",
            "scope_key": "shared_core",
        },
    )
    assert response.status_code == 422
