"""P3.xxE.5: API-level tests for app/api/capability_activation_routes.py --
read-only, tenant-scoped. Mirrors test_entities_routes.py's /
test_process_routes.py's own shape."""

from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.services.analysis_case_orchestration_service import analysis_case_orchestration_service
from app.services.analysis_case_service import AnalysisCaseService, UploadedFile
from app.storage.local_storage import LocalFileStorage

MAINT_CSV = (
    b"asset_id,failure_code,downtime_hours,repair_cost,event_date\n"
    b"V1,brake,4,10000,2026-08-01T08:00:00\n"
    b"V1,brake,5,11000,2026-08-05T08:00:00\n"
    b"V1,brake,6,12000,2026-08-10T08:00:00\n"
)
OPERATIONS_CSV = (
    b"operational_event_id,asset_id,event_date,operational_event_status\n"
    b"OE-1,V1,2026-08-01T10:00:00,completed\n"
)
REVENUE_CSV = b"transaction_amount,event_date,operational_event_id\n5000,2026-08-01T10:00:00,OE-1\n"


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


def _run_case(db: Session, tmp_path: Path, org_id: UUID) -> tuple[UUID, UUID]:
    service = AnalysisCaseService(storage=LocalFileStorage(str(tmp_path)))
    actor = uuid4()
    case = service.create(db, org_id, "Case", "single", actor)
    service.register_artifacts(
        db,
        org_id,
        case.id,
        [
            UploadedFile("maintenance_events.csv", MAINT_CSV),
            UploadedFile("operations_events.csv", OPERATIONS_CSV),
            UploadedFile("revenue_events.csv", REVENUE_CSV),
        ],
        actor,
    )
    run = analysis_case_orchestration_service.start_run(db, org_id, case.id, actor)
    analysis_case_orchestration_service.execute(db, service.storage, org_id, case.id, run.id, actor)
    return case.id, run.id


def test_list_intelligence_capabilities_is_served_from_the_registry(
    client: TestClient, db: Session
) -> None:
    org_id = create_organization(client, "cap-list")
    response = client.get(f"/api/v1/organizations/{org_id}/intelligence-capabilities")
    assert response.status_code == 200, response.text
    rule_codes = {c["rule_code"] for c in response.json()["capabilities"]}
    assert "XDOM-A-ASSET-FAILURE-LOST-ACTIVITY" in rule_codes
    assert "XDOM-B-LOST-ACTIVITY-REVENUE-GAP" in rule_codes


def test_list_activation_decisions_and_shadow_comparison(
    client: TestClient, db: Session, tmp_path: Path
) -> None:
    org_id = create_organization(client, "cap-decisions")
    case_id, run_id = _run_case(db, tmp_path, org_id)

    decisions_response = client.get(
        f"/api/v1/organizations/{org_id}/analysis-cases/{case_id}/activation-decisions",
        params={"run_id": str(run_id)},
    )
    assert decisions_response.status_code == 200, decisions_response.text
    decisions = decisions_response.json()["decisions"]
    assert decisions
    for decision in decisions:
        assert decision["governed_status"] in ("DISABLED", "READY", "PARTIAL", "BLOCKED")
        # P3.xxE.5 Phase 2: both migrated rules are GOVERNED.
        assert decision["mode"] == "governed"

    shadow_response = client.get(
        f"/api/v1/organizations/{org_id}/analysis-cases/{case_id}/shadow-comparison",
        params={"run_id": str(run_id)},
    )
    assert shadow_response.status_code == 200, shadow_response.text
    summary = shadow_response.json()
    assert summary["packs_evaluated"] == len(decisions)
    assert summary["agree_count"] + summary["disagree_count"] == summary["packs_evaluated"]


def test_cross_tenant_activation_decisions_returns_empty_not_other_tenants_data(
    client: TestClient, db: Session, tmp_path: Path
) -> None:
    org_a = create_organization(client, "cap-tenant-a")
    org_b = create_organization(client, "cap-tenant-b")
    case_id, run_id = _run_case(db, tmp_path, org_a)

    response = client.get(
        f"/api/v1/organizations/{org_b}/analysis-cases/{case_id}/activation-decisions",
        params={"run_id": str(run_id)},
    )
    assert response.status_code == 200, response.text
    assert response.json()["decisions"] == []
