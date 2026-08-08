from uuid import UUID, uuid4

from conftest import IdentityState
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from test_commercial_api import commercial_foundation, create_subscription
from test_value_scan_service import governed_finding

from app.models.entities import Finding, OrganizationMembership
from app.models.value_scan import DirectionalValueScan


def test_value_scan_api_creates_reads_replays_and_refuses_without_data(
    client: TestClient,
    db: Session,
    db_engine: Engine,
    identity: IdentityState,
) -> None:
    organization_id, _ = governed_finding(client, db_engine, identity, "value-scan-api-happy")
    path = f"/api/v1/organizations/{organization_id}/value-scans"
    created = client.post(path, json={"idempotency_key": "api:happy"})
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["organization_id"] == str(organization_id)
    assert body["opportunity_count"] == 1
    assert body["is_current"] is True

    replay = client.post(path, json={"idempotency_key": "api:happy"})
    assert replay.status_code == 200
    assert replay.json()["id"] == body["id"]

    read = client.get(f"{path}/{body['id']}")
    assert read.status_code == 200
    assert read.json()["opportunity_snapshot"] == body["opportunity_snapshot"]

    response = client.post(
        "/api/v1/organizations",
        json={
            "name": "Value Scan Empty",
            "slug": "value-scan-empty",
            "country_code": "US",
            "default_currency": "USD",
            "timezone": "UTC",
        },
    )
    assert response.status_code == 201
    empty_id = response.json()["id"]
    refused = client.post(
        f"/api/v1/organizations/{empty_id}/value-scans",
        json={"idempotency_key": "api:empty"},
    )
    assert refused.status_code == 200
    assert refused.json()["status"] == "refused"
    assert refused.json()["next_investigation_snapshot"]["code"] == "RESOLVE_BLOCKING_DATA_GAP"


def test_value_scan_api_enforces_tenant_membership_roles_and_revocation(
    client: TestClient,
    db: Session,
    db_engine: Engine,
    identity: IdentityState,
) -> None:
    organization_id, _ = governed_finding(client, db_engine, identity, "value-scan-api-access")
    path = f"/api/v1/organizations/{organization_id}/value-scans"
    created = client.post(path, json={"idempotency_key": "access:seed"})
    assert created.status_code == 200
    scan_id = created.json()["id"]

    viewer_id = uuid4()
    analyst_id = uuid4()
    for user_id, role in ((viewer_id, "viewer"), (analyst_id, "analyst")):
        membership = client.post(
            f"/api/v1/organizations/{organization_id}/members",
            json={"user_id": str(user_id), "role": role, "status": "active"},
        )
        assert membership.status_code == 201, membership.text

    identity.is_platform_admin = False
    identity.user_id = viewer_id
    assert client.get(f"{path}/{scan_id}").status_code == 200
    assert client.post(path, json={"idempotency_key": "access:viewer"}).status_code == 403

    identity.user_id = analyst_id
    assert client.post(path, json={"idempotency_key": "access:analyst"}).status_code == 200

    db.execute(
        update(OrganizationMembership)
        .where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == analyst_id,
        )
        .values(status="revoked")
    )
    db.commit()
    assert client.get(f"{path}/{scan_id}").status_code == 403
    assert client.post(path, json={"idempotency_key": "access:revoked"}).status_code == 403


def test_value_scan_api_rejects_cross_tenant_get_and_idempotency_conflict(
    client: TestClient,
    db: Session,
    db_engine: Engine,
    identity: IdentityState,
) -> None:
    organization_id, finding = governed_finding(
        client, db_engine, identity, "value-scan-api-conflict"
    )
    other_id, _ = governed_finding(client, db_engine, identity, "value-scan-api-other")
    path = f"/api/v1/organizations/{organization_id}/value-scans"
    created = client.post(path, json={"idempotency_key": "api:conflict"})
    assert created.status_code == 200
    scan_id = created.json()["id"]
    assert client.get(f"/api/v1/organizations/{other_id}/value-scans/{scan_id}").status_code == 404

    db.execute(
        update(Finding)
        .where(Finding.id == finding.id)
        .values(content_fingerprint=uuid4().hex + uuid4().hex)
    )
    db.commit()
    conflict = client.post(path, json={"idempotency_key": "api:conflict"})
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert db.scalar(select(DirectionalValueScan).where(DirectionalValueScan.id == UUID(scan_id)))


def test_value_scan_api_rejects_invalid_payload_and_missing_entitlement(
    client: TestClient,
    db: Session,
    db_engine: Engine,
    identity: IdentityState,
) -> None:
    organization_id, _ = governed_finding(client, db_engine, identity, "value-scan-api-entitlement")
    path = f"/api/v1/organizations/{organization_id}/value-scans"
    assert client.post(path, json={"idempotency_key": ""}).status_code == 422
    assert client.post(path, json={"idempotency_key": "x", "weights": {}}).status_code == 422

    version = commercial_foundation(db)
    create_subscription(client, str(organization_id), str(version.id), key="value-scan:sub")
    member_id = uuid4()
    membership = client.post(
        f"/api/v1/organizations/{organization_id}/members",
        json={"user_id": str(member_id), "role": "analyst", "status": "active"},
    )
    assert membership.status_code == 201
    identity.is_platform_admin = False
    identity.user_id = member_id

    denied = client.post(path, json={"idempotency_key": "api:denied"})
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "ENTITLEMENT_REQUIRED"
    assert (
        db.scalar(
            select(DirectionalValueScan).where(
                DirectionalValueScan.organization_id == organization_id
            )
        )
        is None
    )
