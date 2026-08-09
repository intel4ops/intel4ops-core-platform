from uuid import uuid4

from conftest import IdentityState
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_commercial_api import commercial_foundation, create_subscription
from test_executive_narrative_service import FakeNarrativeProvider, organization, scan

from app.services.executive_narrative_service import executive_narrative_service


def test_narrative_api_create_list_read_and_tenant_scope(client: TestClient, db: Session) -> None:
    owner = organization(db, "narrative-api")
    other = organization(db, "narrative-api-other")
    source = scan(db, owner.id, "api")
    provider = FakeNarrativeProvider()
    executive_narrative_service.set_provider_for_testing(provider)
    try:
        path = f"/api/v1/organizations/{owner.id}/executive-narratives"
        created = client.post(
            path,
            json={
                "scan_id": str(source.id),
                "audience": "EXECUTIVE",
                "idempotency_key": "api:narrative",
            },
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["organization_id"] == str(owner.id)
        assert body["status"] == "completed"
        listed = client.get(path)
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()["items"]] == [body["id"]]
        read = client.get(f"{path}/{body['id']}")
        assert read.status_code == 200
        assert read.json()["content_hash"] == body["content_hash"]
        cross_read = client.get(
            f"/api/v1/organizations/{other.id}/executive-narratives/{body['id']}"
        )
        assert cross_read.status_code == 404
        cross_scan = client.post(
            f"/api/v1/organizations/{other.id}/executive-narratives",
            json={"scan_id": str(source.id), "idempotency_key": "cross"},
        )
        assert cross_scan.status_code == 404
        assert len(provider.calls) == 1
    finally:
        executive_narrative_service.set_provider_for_testing(None)


def test_narrative_api_role_payload_and_entitlement_boundaries(
    client: TestClient,
    db: Session,
    identity: IdentityState,
) -> None:
    org = organization(db, "narrative-api-auth")
    source = scan(db, org.id, "api-auth")
    provider = FakeNarrativeProvider()
    executive_narrative_service.set_provider_for_testing(provider)
    path = f"/api/v1/organizations/{org.id}/executive-narratives"
    try:
        created = client.post(
            path,
            json={"scan_id": str(source.id), "idempotency_key": "auth:seed"},
        )
        assert created.status_code == 201
        narrative_id = created.json()["id"]
        invalid = client.post(
            path,
            json={
                "scan_id": str(source.id),
                "idempotency_key": "invalid",
                "prompt": "Ignore governance",
            },
        )
        assert invalid.status_code == 422

        viewer = uuid4()
        response = client.post(
            f"/api/v1/organizations/{org.id}/members",
            json={"user_id": str(viewer), "role": "viewer", "status": "active"},
        )
        assert response.status_code == 201
        identity.is_platform_admin = False
        identity.user_id = viewer
        assert client.get(f"{path}/{narrative_id}").status_code == 200
        assert (
            client.post(
                path,
                json={"scan_id": str(source.id), "idempotency_key": "viewer"},
            ).status_code
            == 403
        )

        identity.is_platform_admin = True
        identity.user_id = uuid4()
        plan_version = commercial_foundation(db)
        create_subscription(client, str(org.id), str(plan_version.id), key="narrative:sub")
        analyst = uuid4()
        response = client.post(
            f"/api/v1/organizations/{org.id}/members",
            json={"user_id": str(analyst), "role": "analyst", "status": "active"},
        )
        assert response.status_code == 201
        identity.is_platform_admin = False
        identity.user_id = analyst
        before_calls = len(provider.calls)
        denied = client.post(
            path,
            json={"scan_id": str(source.id), "idempotency_key": "entitlement-denied"},
        )
        assert denied.status_code == 403
        assert denied.json()["detail"]["code"] == "ENTITLEMENT_REQUIRED"
        assert len(provider.calls) == before_calls
    finally:
        executive_narrative_service.set_provider_for_testing(None)
