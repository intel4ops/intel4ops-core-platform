from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from conftest import IdentityState
from fastapi.testclient import TestClient
from pydantic import TypeAdapter
from sqlalchemy.orm import Session

from app.models.commercial import (
    Feature,
    IndustryPackDefinition,
    LimitDefinition,
    Plan,
    PlanVersion,
    PlanVersionEntitlement,
    UsageMeterDefinition,
)
from app.services.commercial_service import CommercialServiceError, entitlement_service

JSON_OBJECT = TypeAdapter(dict[str, object])


def organization(client: TestClient, slug: str) -> str:
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


def commercial_foundation(db: Session) -> PlanVersion:
    plan = Plan(code="TEST-GROWTH", name="Test Growth", plan_type="growth", status="active")
    db.add(plan)
    db.flush()
    version = PlanVersion(
        plan_id=plan.id,
        version=1,
        effective_date=date(2026, 1, 1),
        migration_policy="explicit",
        terms={"catalog_version": "test"},
    )
    db.add(version)
    db.flush()
    db.add(
        UsageMeterDefinition(
            code="api_requests",
            product="Platform",
            meter_kind="event",
            unit="requests",
            aggregation="sum",
            currency_behavior="not_applicable",
        )
    )
    feature = Feature(
        key="features.sso",
        name="Enterprise SSO",
        description="Test commercial feature",
        status="active",
    )
    pack = IndustryPackDefinition(
        code="PACK-J2C",
        name="Job-to-Cash",
        entitlement_key="industry.job_to_cash",
        status="planned",
    )
    db.add_all([feature, pack])
    db.flush()
    db.add_all(
        [
            PlanVersionEntitlement(
                plan_version_id=version.id,
                entitlement_type="limit",
                entitlement_key="limits.api_requests",
                enabled=True,
                limit_value=Decimal("10"),
                limit_unit="requests",
                enforcement_type="hard",
                reset_period="monthly",
            ),
            PlanVersionEntitlement(
                plan_version_id=version.id,
                entitlement_type="feature",
                entitlement_key="features.sso",
                enabled=True,
            ),
            PlanVersionEntitlement(
                plan_version_id=version.id,
                entitlement_type="industry_pack",
                entitlement_key="industry.job_to_cash",
                enabled=True,
            ),
            LimitDefinition(
                entitlement_key="limits.api_requests",
                meter_code="api_requests",
                default_enforcement_type="hard",
                default_reset_period="monthly",
                warning_percentage=Decimal("0.8"),
                grace_percentage=Decimal("0"),
            ),
        ]
    )
    db.commit()
    db.refresh(version)
    return version


def create_subscription(
    client: TestClient, organization_id: str, plan_version_id: str, *, key: str = "sub:1"
) -> dict[str, object]:
    now = datetime.now(UTC)
    response = client.post(
        f"/api/v1/organizations/{organization_id}/commercial/subscriptions",
        json={
            "plan_version_id": plan_version_id,
            "idempotency_key": key,
            "status": "active",
            "starts_at": (now - timedelta(days=1)).isoformat(),
            "current_period_start": now.replace(day=1).isoformat(),
            "current_period_end": (now + timedelta(days=30)).isoformat(),
            "renews_at": (now + timedelta(days=30)).isoformat(),
        },
    )
    assert response.status_code == 201, response.text
    return JSON_OBJECT.validate_python(response.json())


def test_commercial_subscription_usage_limits_overrides_and_activation(
    client: TestClient, db: Session
) -> None:
    plan_version = commercial_foundation(db)
    first = organization(client, "commercial-first")
    second = organization(client, "commercial-second")
    subscription = create_subscription(client, first, str(plan_version.id))
    duplicate = create_subscription(client, first, str(plan_version.id))
    assert duplicate["id"] == subscription["id"]
    entitlements = client.get(f"/api/v1/organizations/{first}/commercial/entitlements").json()
    assert {item["entitlement_key"] for item in entitlements} == {
        "limits.api_requests",
        "features.sso",
        "industry.job_to_cash",
    }
    now = datetime.now(UTC)
    payload = {
        "meter_code": "api_requests",
        "idempotency_key": "request:one",
        "quantity": "8",
        "source_type": "api_gateway",
        "source_id": "request-1",
        "occurred_at": now.isoformat(),
    }
    first_event = client.post(
        f"/api/v1/organizations/{first}/commercial/usage-events", json=payload
    )
    assert first_event.status_code == 201, first_event.text
    duplicate_event = client.post(
        f"/api/v1/organizations/{first}/commercial/usage-events", json=payload
    )
    assert duplicate_event.json()["id"] == first_event.json()["id"]
    payload.update(
        {
            "idempotency_key": "request:two",
            "quantity": "1",
            "source_id": "request-2",
        }
    )
    assert (
        client.post(
            f"/api/v1/organizations/{first}/commercial/usage-events", json=payload
        ).status_code
        == 201
    )
    summary = client.get(
        f"/api/v1/organizations/{first}/commercial/usage-summary",
        params={
            "meter_code": "api_requests",
            "period_type": "monthly",
            "at": now.isoformat(),
        },
    )
    assert summary.status_code == 200
    assert summary.json()["quantities"]["NON_CURRENCY"] == "9.000000000000"
    limit = client.get(
        f"/api/v1/organizations/{first}/commercial/limits/limits.api_requests",
        params={"at": now.isoformat()},
    )
    assert limit.status_code == 200, limit.text
    assert limit.json()["status"] == "warning"
    assert limit.json()["remaining"] == "1.000000000000"
    contract = client.post(
        f"/api/v1/organizations/{first}/commercial/contracts",
        json={
            "subscription_id": subscription["id"],
            "contract_code": "EA-2026-01",
            "contract_type": "enterprise",
            "effective_at": now.isoformat(),
            "notes": "Approved negotiated controls.",
        },
    )
    assert contract.status_code == 201, contract.text
    override = client.post(
        f"/api/v1/organizations/{first}/commercial/contracts/{contract.json()['id']}/overrides",
        json={
            "entitlement_key": "limits.api_requests",
            "enabled": True,
            "limit_value": "100",
            "enforcement_type": "soft",
            "effective_at": now.isoformat(),
            "reason": "Signed enterprise agreement.",
            "idempotency_key": "override:api",
        },
    )
    assert override.status_code == 201, override.text
    negotiated_limit = client.get(
        f"/api/v1/organizations/{first}/commercial/limits/limits.api_requests",
        params={"at": (now + timedelta(seconds=1)).isoformat()},
    )
    assert negotiated_limit.status_code == 200, negotiated_limit.text
    assert negotiated_limit.json()["limit_value"] == "100.000000000000"
    assert negotiated_limit.json()["status"] == "available"
    feature = client.put(
        f"/api/v1/organizations/{first}/commercial/feature-flags",
        json={
            "feature_key": "features.sso",
            "enabled": True,
            "effective_at": now.isoformat(),
            "reason": "Enabled under Growth plan.",
        },
    )
    assert feature.status_code == 200, feature.text
    pack = client.post(
        f"/api/v1/organizations/{first}/commercial/industry-packs",
        json={"pack_code": "PACK-J2C", "effective_at": now.isoformat()},
    )
    assert pack.status_code == 201, pack.text
    assert client.get(f"/api/v1/organizations/{second}/commercial/subscriptions").json() == []
    assert client.get(f"/api/v1/organizations/{second}/commercial/usage-events").json() == []


def test_trial_expiry_and_plan_version_immutability(client: TestClient, db: Session) -> None:
    version = commercial_foundation(db)
    org = organization(client, "commercial-trial")
    now = datetime.now(UTC)
    response = client.post(
        f"/api/v1/organizations/{org}/commercial/subscriptions",
        json={
            "plan_version_id": str(version.id),
            "idempotency_key": "trial:expired",
            "status": "trial",
            "starts_at": (now - timedelta(days=10)).isoformat(),
            "current_period_start": (now - timedelta(days=10)).isoformat(),
            "current_period_end": (now + timedelta(days=10)).isoformat(),
            "trial_ends_at": (now - timedelta(days=1)).isoformat(),
        },
    )
    assert response.status_code == 201
    with pytest.raises(CommercialServiceError, match="Trial has expired"):
        entitlement_service.require(db, UUID(org), "features.sso")
    version.migration_policy = "immediate"
    with pytest.raises(ValueError, match="immutable"):
        db.commit()
    db.rollback()


def test_assigned_subscription_enforces_entitlements_after_membership_authorization(
    client: TestClient, db: Session, identity: IdentityState
) -> None:
    version = commercial_foundation(db)
    org = organization(client, "commercial-enforcement")
    member_id = UUID("3cb443cd-d982-4da0-9968-f24af106f586")
    membership = client.post(
        f"/api/v1/organizations/{org}/members",
        json={"user_id": str(member_id), "role": "viewer", "status": "active"},
    )
    assert membership.status_code == 201, membership.text
    create_subscription(client, org, str(version.id), key="sub:enforcement")

    identity.user_id = member_id
    identity.is_platform_admin = False
    denied = client.get(f"/api/v1/organizations/{org}/source-systems")
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "ENTITLEMENT_REQUIRED"

    identity.is_platform_admin = True
    allowed = client.get(f"/api/v1/organizations/{org}/source-systems")
    assert allowed.status_code == 200
