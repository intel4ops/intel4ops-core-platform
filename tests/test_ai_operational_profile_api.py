from uuid import UUID, uuid4

from conftest import IdentityState
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from test_ai_operational_profile_service import FakeProvider, item
from test_commercial_api import commercial_foundation, create_subscription

from app.models.entities import OrganizationMembership
from app.models.workspace import OrganizationObjective
from app.services.ai_operational_profile_service import ai_operational_profile_service


def create_organization(client: TestClient, slug: str) -> UUID:
    response = client.post(
        "/api/v1/organizations",
        json={
            "name": slug,
            "slug": f"{slug}-{uuid4().hex[:8]}",
            "country_code": "US",
            "default_currency": "USD",
            "timezone": "UTC",
        },
    )
    assert response.status_code == 201, response.text
    return UUID(response.json()["id"])


def test_profile_api_create_read_confirm_reject_and_cross_tenant_scope(
    client: TestClient, db: Session
) -> None:
    org = create_organization(client, "profile-api")
    other = create_organization(client, "profile-api-other")
    provider = FakeProvider(
        [
            item("BUSINESS_OBJECTIVE", "reduce_downtime", f"organization:{org}"),
            item("OPERATIONAL_CHALLENGE", "downtime", f"organization:{org}"),
        ]
    )
    ai_operational_profile_service.set_provider_for_testing(provider)
    try:
        path = f"/api/v1/organizations/{org}/operational-profiles"
        created = client.post(path, json={"idempotency_key": "api:1"})
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["status"] == "completed"
        assert len(body["inferences"]) == 2
        assert client.get(f"{path}/{body['id']}").status_code == 200
        assert (
            client.get(
                f"/api/v1/organizations/{other}/operational-profiles/{body['id']}"
            ).status_code
            == 404
        )

        confirmed = client.post(
            f"{path}/{body['id']}/inferences/{body['inferences'][0]['id']}/confirm",
            json={"decision": "CONFIRM"},
        )
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["status"] == "CONFIRMED"
        assert db.scalar(
            select(OrganizationObjective).where(
                OrganizationObjective.organization_id == org,
                OrganizationObjective.objective_code == "reduce_downtime",
            )
        )
        rejected = client.post(
            f"{path}/{body['id']}/inferences/{body['inferences'][1]['id']}/reject"
        )
        assert rejected.status_code == 200
        assert rejected.json()["status"] == "REJECTED"
    finally:
        ai_operational_profile_service.set_provider_for_testing(None)


def test_profile_api_authorization_revocation_and_payload_boundary(
    client: TestClient,
    db: Session,
    db_engine: Engine,
    identity: IdentityState,
) -> None:
    org = create_organization(client, "profile-auth")
    provider = FakeProvider([item("INDUSTRY", "manufacturing", f"organization:{org}")])
    ai_operational_profile_service.set_provider_for_testing(provider)
    try:
        path = f"/api/v1/organizations/{org}/operational-profiles"
        created = client.post(path, json={"idempotency_key": "auth:seed"})
        assert created.status_code == 201
        body = created.json()
        assert (
            client.post(path, json={"idempotency_key": "", "prompt": "arbitrary"}).status_code
            == 422
        )

        viewer = uuid4()
        analyst = uuid4()
        for user_id, role in ((viewer, "viewer"), (analyst, "analyst")):
            response = client.post(
                f"/api/v1/organizations/{org}/members",
                json={"user_id": str(user_id), "role": role, "status": "active"},
            )
            assert response.status_code == 201

        identity.is_platform_admin = False
        identity.user_id = viewer
        assert client.get(f"{path}/{body['id']}").status_code == 200
        assert client.post(path, json={"idempotency_key": "viewer"}).status_code == 403
        confirm_url = f"{path}/{body['id']}/inferences/{body['inferences'][0]['id']}/confirm"
        assert client.post(confirm_url, json={"decision": "CONFIRM"}).status_code == 403

        identity.user_id = analyst
        assert client.post(path, json={"idempotency_key": "analyst"}).status_code == 201
        with Session(db_engine) as worker:
            worker.execute(
                update(OrganizationMembership)
                .where(
                    OrganizationMembership.organization_id == org,
                    OrganizationMembership.user_id == analyst,
                )
                .values(status="revoked")
            )
            worker.commit()
        assert client.get(f"{path}/{body['id']}").status_code == 403
        assert client.post(path, json={"idempotency_key": "revoked"}).status_code == 403
    finally:
        ai_operational_profile_service.set_provider_for_testing(None)


def test_profile_api_reuses_intelligence_findings_entitlement(
    client: TestClient,
    db: Session,
    identity: IdentityState,
) -> None:
    org = create_organization(client, "profile-entitlement")
    plan_version = commercial_foundation(db)
    create_subscription(client, str(org), str(plan_version.id), key="profile-entitlement:sub")
    analyst = uuid4()
    membership = client.post(
        f"/api/v1/organizations/{org}/members",
        json={"user_id": str(analyst), "role": "analyst", "status": "active"},
    )
    assert membership.status_code == 201
    provider = FakeProvider([])
    ai_operational_profile_service.set_provider_for_testing(provider)
    identity.is_platform_admin = False
    identity.user_id = analyst
    try:
        response = client.post(
            f"/api/v1/organizations/{org}/operational-profiles",
            json={"idempotency_key": "entitlement:denied"},
        )
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "ENTITLEMENT_REQUIRED"
        assert provider.calls == []
    finally:
        ai_operational_profile_service.set_provider_for_testing(None)
