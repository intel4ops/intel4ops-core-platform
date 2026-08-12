from datetime import UTC, date, datetime
from io import BytesIO
from typing import cast
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from test_finding_platform import create_execution, publish
from test_findings_tenancy import create_organization, finding_payload
from test_industry_packs import PACKS
from test_industry_packs import _foundation as industry_pack_foundation
from test_operational_signatures import _execution_payload
from test_operational_signatures import _foundation as signature_foundation

from app.main import app
from app.models.entities import Finding, FindingGovernanceTier
from app.schemas.industry_packs import PackAssignmentRequest, PackExecutionCreate
from app.schemas.job_to_cash import CanonicalRecord, JobToCashRunCreate
from app.schemas.signatures import SignatureDeploymentCreate
from app.services.finding_service import FindingService
from app.services.industry_pack_service import tenant_industry_pack_service
from app.services.job_to_cash_orchestration_service import job_to_cash_orchestration_service
from app.services.signature_service import tenant_signature_service

LEGACY_ROUTES = {
    ("POST", "/api/v1/intelligence/maintenance/analyze"),
    ("GET", "/api/v1/command/findings"),
    ("POST", "/api/v1/recovery/actions"),
}


# --- A: governed publication -> GOVERNED ------------------------------------


def test_governed_publication_sets_governance_tier_governed(
    client: TestClient,
    db_engine: Engine,
    identity: "object",
) -> None:
    organization_id, execution_id = create_execution(client, "gov-tier-a")
    finding = publish(db_engine, organization_id, execution_id, identity.user_id)  # type: ignore[attr-defined]
    assert finding.governance_tier == FindingGovernanceTier.GOVERNED.value


# --- B: FindingService.create -> LIGHTWEIGHT --------------------------------


def test_finding_service_create_sets_governance_tier_lightweight(db: Session) -> None:
    org = create_organization(db, "gov-tier-b")
    finding = FindingService().create(db, org.id, finding_payload("Lightweight direct"))
    assert finding.governance_tier == FindingGovernanceTier.LIGHTWEIGHT.value


# --- C: Job-to-Cash -> LIGHTWEIGHT -------------------------------------------


def test_job_to_cash_finding_sets_governance_tier_lightweight(db: Session) -> None:
    org = create_organization(db, "gov-tier-c")
    actor = uuid4()
    payload = JobToCashRunCreate(
        idempotency_key="gov-tier-c-run",
        currency_code="USD",
        as_of=date(2026, 3, 1),
        records=[
            CanonicalRecord(
                type="job",
                id="J1",
                data={
                    "status": "completed",
                    "completed_at": "2026-01-01",
                    "billing_window_days": 5,
                    "contractual_charges": "100",
                },
            )
        ],
    )
    run = job_to_cash_orchestration_service.execute(db, org.id, payload, actor)
    assert int(cast(int, run.reconciliation["finding_count"])) >= 1
    findings = list(db.scalars(select(Finding).where(Finding.organization_id == org.id)))
    assert findings
    assert all(item.governance_tier == FindingGovernanceTier.LIGHTWEIGHT.value for item in findings)


# --- D: Industry Pack -> LIGHTWEIGHT -----------------------------------------


def test_industry_pack_finding_sets_governance_tier_lightweight(db: Session) -> None:
    organization = industry_pack_foundation(db)
    actor = uuid4()
    code, _name, _industry, _entitlement = next(item for item in PACKS if item[0] == "PACK-MFG")
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
    payload = PackExecutionCreate(
        idempotency_key="gov-tier-d-execute",
        readiness="ready",
        rule_code="MFG-DOWNTIME",
        record={
            "record_id": "record:MFG-DOWNTIME",
            "observed_at": "2026-07-27T00:00:00Z",
            "value": "12",
            "threshold": "10",
        },
    )
    result = tenant_industry_pack_service.execute(
        db, organization.id, assignment.assignment_id, payload, actor
    )
    assert result.result_json["triggered"] is True
    # NOTE: result_json["finding_id"] is unreliable here (pre-existing, unrelated
    # defect: the in-place mutation of the shared `result` dict after the first
    # db.flush() is not detected by SQLAlchemy's change tracking, so it is never
    # persisted). Query the created Finding directly instead.
    finding = db.scalar(
        select(Finding).where(
            Finding.organization_id == organization.id,
            Finding.rule_id == "MFG-DOWNTIME",
        )
    )
    assert finding is not None
    assert finding.governance_tier == FindingGovernanceTier.LIGHTWEIGHT.value


# --- E: Operational Signature -> LIGHTWEIGHT ---------------------------------


def test_signature_finding_sets_governance_tier_lightweight(db: Session) -> None:
    organization, _signature, version, actor = signature_foundation(db)
    deployment = tenant_signature_service.deploy(
        db,
        organization.id,
        SignatureDeploymentCreate(signature_version_id=version.id),
        actor,
    )
    execution = tenant_signature_service.execute(
        db, organization.id, deployment.id, _execution_payload("gov-tier-e"), actor
    )
    assert execution.matched is True
    finding = db.scalar(
        select(Finding).where(
            Finding.id == execution.finding_id,
            Finding.organization_id == organization.id,
        )
    )
    assert finding is not None
    assert finding.governance_tier == FindingGovernanceTier.LIGHTWEIGHT.value


# --- F: maintenance demo -> LIGHTWEIGHT --------------------------------------


def test_maintenance_demo_finding_sets_governance_tier_lightweight(
    client: TestClient, db_engine: Engine
) -> None:
    organization = client.post(
        "/api/v1/organizations",
        json={
            "name": "gov-tier-f",
            "slug": "gov-tier-f",
            "country_code": "US",
            "default_currency": "USD",
            "timezone": "UTC",
        },
    ).json()
    csv_body = (
        b"asset_id,failure_code,downtime_hours,repair_cost\n"
        b"BUS-1,BRAKE,4,200\n"
        b"BUS-1,BRAKE,5,250\n"
        b"BUS-1,BRAKE,6,300\n"
    )
    response = client.post(
        "/api/v1/intelligence/maintenance/analyze",
        params={"organization_id": organization["id"]},
        files={"file": ("failures.csv", BytesIO(csv_body), "text/csv")},
    )
    assert response.status_code == 200
    findings = response.json()
    assert len(findings) == 1
    with Session(db_engine) as db:
        finding = db.get(Finding, UUID(findings[0]["id"]))
        assert finding is not None
        assert finding.governance_tier == FindingGovernanceTier.LIGHTWEIGHT.value


# --- G/H/I: canonical findings list default/explicit/mixed filtering --------


def _mixed_tenant_findings(db: Session, slug: str) -> tuple[UUID, Finding, Finding]:
    org = create_organization(db, slug)
    governed = Finding(
        organization_id=org.id,
        governance_tier=FindingGovernanceTier.GOVERNED.value,
        rule_id="GOV.TEST",
        finding_code=f"FND-{uuid4().hex[:10].upper()}",
        finding_type="leakage",
        title="Governed row",
        summary="Governed canonical row",
        domain="quality",
        domain_code="quality",
        severity="high",
        confidence_score=0.9,
        confidence_level="high",
        status="published",
        measured_value=1,
        measured_value_type="currency",
        detected_at=datetime.now(UTC),
        definition_code="GOV.TEST",
        definition_version="1.0.0",
        source_execution_id=None,
        deduplication_key=uuid4().hex,
    )
    lightweight = Finding(
        organization_id=org.id,
        governance_tier=FindingGovernanceTier.LIGHTWEIGHT.value,
        rule_id="LW.TEST",
        finding_code=f"FND-{uuid4().hex[:10].upper()}",
        finding_type="deterministic_rule",
        title="Lightweight row",
        summary="Lightweight canonical row",
        domain="quality",
        domain_code="quality",
        severity="high",
        confidence_score=0.9,
        confidence_level="high",
        status="published",
        measured_value=1,
        measured_value_type="currency",
        detected_at=datetime.now(UTC),
        definition_code="LW.TEST",
        definition_version="1.0.0",
        deduplication_key=uuid4().hex,
    )
    db.add_all([governed, lightweight])
    db.commit()
    db.refresh(governed)
    db.refresh(lightweight)
    return org.id, governed, lightweight


def test_default_findings_list_returns_governed_only(client: TestClient, db: Session) -> None:
    organization_id, governed, lightweight = _mixed_tenant_findings(db, "gov-tier-g")
    response = client.get(f"/api/v1/organizations/{organization_id}/findings")
    assert response.status_code == 200
    body = response.json()
    ids = {item["id"] for item in body["items"]}
    assert str(governed.id) in ids
    assert str(lightweight.id) not in ids
    assert all(item["governance_tier"] == "GOVERNED" for item in body["items"])


def test_explicit_lightweight_query_returns_lightweight_only(
    client: TestClient, db: Session
) -> None:
    organization_id, governed, lightweight = _mixed_tenant_findings(db, "gov-tier-h")
    response = client.get(
        f"/api/v1/organizations/{organization_id}/findings",
        params={"governance_tier": "LIGHTWEIGHT"},
    )
    assert response.status_code == 200
    body = response.json()
    ids = {item["id"] for item in body["items"]}
    assert str(lightweight.id) in ids
    assert str(governed.id) not in ids
    assert all(item["governance_tier"] == "LIGHTWEIGHT" for item in body["items"])


def test_mixed_tenant_default_list_never_leaks_lightweight(client: TestClient, db: Session) -> None:
    organization_id, governed, lightweight = _mixed_tenant_findings(db, "gov-tier-i")
    response = client.get(
        f"/api/v1/organizations/{organization_id}/findings",
        params={"page_size": 100},
    )
    body = response.json()
    assert body["total"] == 1
    assert [item["id"] for item in body["items"]] == [str(governed.id)]


# --- J/K: tenant isolation on governance-tier queries ------------------------


def test_tenant_a_governed_query_excludes_tenant_b(client: TestClient, db: Session) -> None:
    org_a, governed_a, _lightweight_a = _mixed_tenant_findings(db, "gov-tier-j-a")
    org_b, governed_b, _lightweight_b = _mixed_tenant_findings(db, "gov-tier-j-b")
    response = client.get(f"/api/v1/organizations/{org_a}/findings")
    ids = {item["id"] for item in response.json()["items"]}
    assert str(governed_a.id) in ids
    assert str(governed_b.id) not in ids


def test_tenant_a_lightweight_query_excludes_tenant_b(client: TestClient, db: Session) -> None:
    org_a, _governed_a, lightweight_a = _mixed_tenant_findings(db, "gov-tier-k-a")
    org_b, _governed_b, lightweight_b = _mixed_tenant_findings(db, "gov-tier-k-b")
    response = client.get(
        f"/api/v1/organizations/{org_a}/findings",
        params={"governance_tier": "LIGHTWEIGHT"},
    )
    ids = {item["id"] for item in response.json()["items"]}
    assert str(lightweight_a.id) in ids
    assert str(lightweight_b.id) not in ids


# --- U/V: legacy route isolation ---------------------------------------------


def test_legacy_routes_remain_callable(client: TestClient, db_engine: Engine) -> None:
    organization = client.post(
        "/api/v1/organizations",
        json={
            "name": "gov-tier-legacy",
            "slug": "gov-tier-legacy",
            "country_code": "US",
            "default_currency": "USD",
            "timezone": "UTC",
        },
    ).json()
    findings_response = client.get(
        "/api/v1/command/findings", params={"organization_id": organization["id"]}
    )
    assert findings_response.status_code == 200
    with Session(db_engine) as db:
        finding = FindingService().create(
            db, UUID(organization["id"]), finding_payload("Legacy recovery target")
        )
        finding_id = finding.id
    recovery_response = client.post(
        "/api/v1/recovery/actions",
        params={"organization_id": organization["id"]},
        json={"finding_id": str(finding_id), "title": "Recover it", "owner": "ops"},
    )
    assert recovery_response.status_code == 200
    csv_body = b"asset_id,failure_code,downtime_hours,repair_cost\nBUS-1,BRAKE,4,200\n"
    analyze_response = client.post(
        "/api/v1/intelligence/maintenance/analyze",
        params={"organization_id": organization["id"]},
        files={"file": ("failures.csv", BytesIO(csv_body), "text/csv")},
    )
    assert analyze_response.status_code == 200


def test_legacy_routes_absent_from_openapi_schema() -> None:
    schema = app.openapi()
    documented_routes = {
        (method.upper(), path) for path, methods in schema["paths"].items() for method in methods
    }
    for route in LEGACY_ROUTES:
        assert route not in documented_routes, f"{route} must be hidden from OpenAPI"
