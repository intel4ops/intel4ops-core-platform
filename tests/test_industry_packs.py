from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.industry_packs.catalog import MANIFESTS, PACKS, components
from app.models.commercial import (
    Entitlement,
    IndustryPackDefinition,
    Plan,
    PlanVersion,
    Subscription,
    UsageEvent,
    UsageMeterDefinition,
)
from app.models.economics import RecoveryOpportunity
from app.models.entities import Finding, FindingEvidence, Organization, RecoveryAction
from app.models.gateway import ApplicationClient, JobToCashRun
from app.models.industry_packs import (
    IndustryPackComponent,
    IndustryPackGovernanceEvent,
    IndustryPackVersion,
)
from app.schemas.industry_packs import (
    PackAssignmentRequest,
    PackComponentWrite,
    PackExecutionCreate,
    PackVersionCreate,
)
from app.services.commercial_service import CommercialServiceError
from app.services.industry_pack_service import governance_service, tenant_industry_pack_service


def _foundation(db: Session) -> Organization:
    organization = Organization(
        name="Pack Tenant",
        slug="pack-tenant",
        country_code="US",
        default_currency="USD",
        timezone="UTC",
        status="active",
        is_demo=True,
    )
    db.add(organization)
    db.flush()
    plan = Plan(
        code="PACK-TEST-PLAN",
        name="Pack Test Plan",
        plan_type="enterprise",
        status="active",
    )
    db.add(plan)
    db.flush()
    plan_version = PlanVersion(
        plan_id=plan.id,
        version=1,
        effective_date=date(2026, 1, 1),
        migration_policy="explicit",
        terms={},
    )
    db.add(plan_version)
    db.flush()
    now = datetime.now(UTC)
    subscription = Subscription(
        organization_id=organization.id,
        plan_version_id=plan_version.id,
        idempotency_key="pack-test-subscription",
        status="active",
        starts_at=now - timedelta(days=1),
        current_period_start=now - timedelta(days=1),
        current_period_end=now + timedelta(days=30),
        created_by_user_id=uuid4(),
    )
    db.add(subscription)
    db.flush()
    db.add_all(
        [
            UsageMeterDefinition(
                code=code,
                product="Intelligence",
                meter_kind="event",
                unit="executions" if code == "rule_executions" else "rows",
                aggregation="sum",
                currency_behavior="not_applicable",
            )
            for code in ("rule_executions", "rows_processed")
        ]
    )
    db.add(
        ApplicationClient(
            client_code="intel4ops-web",
            name="Intel4Ops Web",
            client_type="first_party",
            status="active",
        )
    )
    for code, name, _industry, entitlement in PACKS:
        pack = IndustryPackDefinition(
            code=code, name=name, entitlement_key=entitlement, status="active"
        )
        db.add(pack)
        db.flush()
        version = IndustryPackVersion(
            pack_id=pack.id,
            semantic_version="1.0.0",
            lifecycle_status="published",
            manifest_json=MANIFESTS[code],
            minimum_platform_revision="20260726_0018",
            published_at=datetime.now(UTC),
        )
        db.add(version)
        db.flush()
        for item in components(code):
            db.add(
                IndustryPackComponent(
                    pack_version_id=version.id,
                    component_type=str(item["type"]),
                    code=str(item["code"]),
                    universal_parent=str(item["universal_parent"]),
                    configuration=item["config"],
                )
            )
        db.add(
            Entitlement(
                organization_id=organization.id,
                subscription_id=subscription.id,
                entitlement_type="industry_pack",
                entitlement_key=entitlement,
                enabled=True,
                source="plan",
                effective_at=now - timedelta(days=1),
                idempotency_key=f"entitlement:{code}",
                granted_by_user_id=uuid4(),
            )
        )
    db.commit()
    db.refresh(organization)
    return organization


def test_manifests_have_governed_universal_components() -> None:
    assert set(MANIFESTS) == {"PACK-J2C", "PACK-MFG", "PACK-PORTS", "PACK-MOB"}
    for manifest in MANIFESTS.values():
        assert governance_service._manifest_errors(manifest) == []
        items = manifest["components"]
        assert isinstance(items, list)
        assert len([item for item in items if item["type"] == "rule_binding"]) == 6
        assert len([item for item in items if item["type"] == "recovery_playbook"]) == 6
        assert all(item["universal_parent"] for item in items)


def test_version_lifecycle_is_audited_and_published_components_are_immutable(
    db: Session,
) -> None:
    actor = uuid4()
    pack = IndustryPackDefinition(
        code="PACK-TEST",
        name="Test Pack",
        entitlement_key="industry.test",
        status="draft",
    )
    db.add(pack)
    db.commit()
    version = governance_service.create_version(
        db,
        pack.code,
        PackVersionCreate(
            semantic_version="1.0.0",
            manifest_json={
                **MANIFESTS["PACK-MFG"],
                "pack_code": pack.code,
                "entitlement_key": pack.entitlement_key,
            },
        ),
        actor,
    )
    governance_service.validate(db, version.id, actor, "validation passed")
    governance_service.transition(db, version.id, "approved", actor, "owner approval")
    published = governance_service.transition(
        db, version.id, "published", actor, "release approval"
    )
    assert published.lifecycle_status == "published"
    assert (
        db.scalar(
            select(func.count())
            .select_from(IndustryPackGovernanceEvent)
            .where(IndustryPackGovernanceEvent.pack_version_id == version.id)
        )
        == 4
    )
    with pytest.raises(CommercialServiceError, match="Expected draft"):
        governance_service.put_component(
            db,
            version.id,
            PackComponentWrite(
                component_type="metric_definition",
                code="MFG.EXPOSURE",
                universal_parent="metrics.exposure",
            ),
            actor,
        )


def test_four_pack_execution_is_tenant_scoped_idempotent_and_metered(db: Session) -> None:
    organization = _foundation(db)
    actor = uuid4()
    rule_codes = ("J2C-CNI-001", "MFG-DOWNTIME", "PORT-BERTH", "MOB-TRIP")
    for (code, _name, _industry, _entitlement), rule_code in zip(PACKS, rule_codes, strict=True):
        assignment = tenant_industry_pack_service.assign(
            db,
            organization.id,
            PackAssignmentRequest(
                pack_code=code,
                semantic_version="1.0.0",
                effective_at=datetime.now(UTC),
            ),
            actor,
        )
        tenant_industry_pack_service.set_status(
            db,
            organization.id,
            assignment.assignment_id,
            "active",
            actor,
            "test activation",
        )
        record: dict[str, object] = {
            "record_id": f"record:{code}",
            "observed_at": "2026-07-27T00:00:00Z",
            "value": "12",
            "threshold": "10",
        }
        if code == "PACK-J2C":
            record = {
                "currency_code": "USD",
                "as_of": "2026-03-01",
                "records": [
                    {
                        "type": "job",
                        "id": "J1",
                        "data": {
                            "status": "completed",
                            "completed_at": "2026-01-01",
                            "billing_window_days": 5,
                            "contractual_charges": "100",
                        },
                    }
                ],
            }
        payload = PackExecutionCreate(
            idempotency_key=f"execute:{code}",
            readiness="ready",
            rule_code=rule_code,
            record=record,
        )
        first = tenant_industry_pack_service.execute(
            db, organization.id, assignment.assignment_id, payload, actor
        )
        repeated = tenant_industry_pack_service.execute(
            db, organization.id, assignment.assignment_id, payload, actor
        )
        assert repeated.id == first.id
        assert first.status == "completed"
        if code == "PACK-J2C":
            assert first.result_json["runtime"] == "wp_2_18_job_to_cash"
            assert first.result_json["finding_count"] == 1
        else:
            assert first.result_json["triggered"] is True
        assert first.result_json["recovery_playbook_code"] == f"{rule_code}.RECOVERY"

    assert db.scalar(select(func.count()).select_from(UsageEvent)) == 6
    assert db.scalar(select(func.count()).select_from(Finding)) == 4
    assert db.scalar(select(func.count()).select_from(FindingEvidence)) == 4
    assert db.scalar(select(func.count()).select_from(RecoveryOpportunity)) == 4
    assert db.scalar(select(func.count()).select_from(RecoveryAction)) == 4
    assert db.scalar(select(func.count()).select_from(JobToCashRun)) == 1
    with pytest.raises(CommercialServiceError, match="not found"):
        tenant_industry_pack_service.execute(db, uuid4(), assignment.assignment_id, payload, actor)


def test_blocked_readiness_does_not_run_rule(db: Session) -> None:
    organization = _foundation(db)
    actor = uuid4()
    assignment = tenant_industry_pack_service.assign(
        db,
        organization.id,
        PackAssignmentRequest(
            pack_code="PACK-MFG",
            semantic_version="1.0.0",
            effective_at=datetime.now(UTC),
        ),
        actor,
    )
    tenant_industry_pack_service.set_status(
        db,
        organization.id,
        assignment.assignment_id,
        "active",
        actor,
        "test activation",
    )
    execution = tenant_industry_pack_service.execute(
        db,
        organization.id,
        assignment.assignment_id,
        PackExecutionCreate(
            idempotency_key="blocked",
            readiness="blocked",
            rule_code="MFG-DOWNTIME",
            record={"value": 12, "threshold": 10},
        ),
        actor,
    )
    assert execution.status == "blocked"
    assert execution.error_code == "TRUST_READINESS_BLOCKED"


def test_pack_assignment_requires_explicit_commercial_entitlement(db: Session) -> None:
    _foundation(db)
    unentitled = Organization(
        name="Unentitled Tenant",
        slug="unentitled-pack-tenant",
        country_code="US",
        default_currency="USD",
        timezone="UTC",
        status="active",
        is_demo=True,
    )
    db.add(unentitled)
    db.commit()
    with pytest.raises(CommercialServiceError) as exc:
        tenant_industry_pack_service.assign(
            db,
            unentitled.id,
            PackAssignmentRequest(
                pack_code="PACK-MFG",
                semantic_version="1.0.0",
                effective_at=datetime.now(UTC),
            ),
            uuid4(),
        )
    assert exc.value.code == "ENTITLEMENT_REQUIRED"


def test_industry_pack_api_catalog_assignment_activation_and_execution(
    client: TestClient, db: Session
) -> None:
    organization = _foundation(db)
    catalog = client.get("/api/v1/industry-packs")
    assert catalog.status_code == 200
    assert {item["code"] for item in catalog.json()} == {
        "PACK-J2C",
        "PACK-MFG",
        "PACK-PORTS",
        "PACK-MOB",
    }
    assigned = client.post(
        f"/api/v1/organizations/{organization.id}/industry-packs",
        json={
            "pack_code": "PACK-PORTS",
            "semantic_version": "1.0.0",
            "effective_at": datetime.now(UTC).isoformat(),
        },
    )
    assert assigned.status_code == 201, assigned.text
    assignment_id = assigned.json()["assignment_id"]
    activated = client.post(
        f"/api/v1/organizations/{organization.id}/industry-packs/{assignment_id}/status/active",
        json={"reason": "approved test activation"},
    )
    assert activated.status_code == 200, activated.text
    executed = client.post(
        f"/api/v1/organizations/{organization.id}/industry-packs/{assignment_id}/executions",
        json={
            "idempotency_key": "api:ports:one",
            "readiness": "ready",
            "rule_code": "PORT-BERTH",
            "record": {
                "record_id": "berth-1",
                "observed_at": "2026-07-27T00:00:00Z",
                "value": 15,
                "threshold": 10,
            },
        },
    )
    assert executed.status_code == 201, executed.text
    assert executed.json()["result_json"]["recovery_playbook_code"] == "PORT-BERTH.RECOVERY"
    for path, expected_type, expected_count in (
        ("metrics", "metric_definition", 1),
        ("rules", "rule_binding", 6),
        ("playbooks", "recovery_playbook", 6),
    ):
        metadata = client.get(
            f"/api/v1/organizations/{organization.id}/industry-packs/{assignment_id}/{path}"
        )
        assert metadata.status_code == 200, metadata.text
        assert len(metadata.json()) == expected_count
        assert {item["component_type"] for item in metadata.json()} == {expected_type}
    capabilities = client.get(
        f"/api/v1/organizations/{organization.id}/industry-packs/{assignment_id}/capabilities"
    )
    assert capabilities.status_code == 200
    assert capabilities.json()["semantic_version"] == "1.0.0"
    history = client.get(
        f"/api/v1/organizations/{organization.id}/industry-packs/{assignment_id}/executions"
    )
    assert history.status_code == 200
    assert [item["id"] for item in history.json()] == [executed.json()["id"]]
    detail = client.get(
        f"/api/v1/organizations/{organization.id}/industry-packs/"
        f"{assignment_id}/executions/{executed.json()['id']}"
    )
    assert detail.status_code == 200
    assert detail.json()["id"] == executed.json()["id"]
    unregistered = client.get(
        "/api/v1/industry-packs",
        headers={"X-Intel4Ops-Client": "unregistered-client"},
    )
    assert unregistered.status_code == 400
    assert unregistered.json()["detail"]["code"] == "CLIENT_NOT_REGISTERED"
    other_tenant = uuid4()
    assert (
        client.post(
            f"/api/v1/organizations/{other_tenant}/industry-packs/{assignment_id}/executions",
            json={
                "idempotency_key": "api:cross-tenant",
                "readiness": "ready",
                "rule_code": "PORT-BERTH",
                "record": {"value": 15, "threshold": 10},
            },
        ).status_code
        == 404
    )
