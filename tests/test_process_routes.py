"""P3.xxE.4: API-level tests for app/api/process_routes.py -- read-only,
tenant-scoped. Mirrors test_entities_routes.py's own shape.

Two datasets, both keyed by work_order_id, mirroring
test_entities_order_independence.py's own documented fixture-shape
lesson: a single-dataset fixture's identifier field caps out around
accepted_with_flag (~0.85) and never reaches auto_accepted, producing
zero typed entities -- cross-dataset corroboration is what actually
clears the deterministic confidence engine's threshold. Splitting
schedule/complete across two datasets also gives activity_discovery.py's
own corroboration gate a genuine cross-dataset signal."""

from pathlib import Path
from uuid import UUID, uuid4

from conftest import IdentityState
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.services.analysis_case_orchestration_service import analysis_case_orchestration_service
from app.services.analysis_case_service import AnalysisCaseService, UploadedFile
from app.storage.local_storage import LocalFileStorage

WORK_ORDERS_CSV = (
    b"work_order_id,scheduled_at,status\n"
    + b"\n".join(f"WO-{i + 1},2026-01-{i + 1:02d}T08:00:00,completed".encode() for i in range(12))
    + b"\n"
)
WORK_ORDER_COMPLETIONS_CSV = (
    b"work_order_id,completed_at\n"
    + b"\n".join(f"WO-{i + 1},2026-01-{i + 1:02d}T17:00:00".encode() for i in range(12))
    + b"\n"
)


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
            UploadedFile("work_orders.csv", WORK_ORDERS_CSV),
            UploadedFile("work_order_completions.csv", WORK_ORDER_COMPLETIONS_CSV),
        ],
        actor,
    )
    run = analysis_case_orchestration_service.start_run(db, org_id, case.id, actor)
    analysis_case_orchestration_service.execute(db, service.storage, org_id, case.id, run.id, actor)
    return case.id, run.id


def test_list_processes_returns_a_well_shaped_response(
    client: TestClient, db: Session, tmp_path: Path
) -> None:
    org_id = create_organization(client, "proc-list")
    case_id, run_id = _run_case(db, tmp_path, org_id)

    response = client.get(
        f"/api/v1/organizations/{org_id}/analysis-cases/{case_id}/processes",
        params={"run_id": str(run_id)},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["run_id"] == str(run_id)
    assert isinstance(body["processes"], list)
    for process in body["processes"]:
        assert 0.0 <= process["overall_confidence"] <= 1.0
        assert process["boundary_status"] in {
            "LEFT_CENSORED",
            "RIGHT_CENSORED",
            "PARTIAL",
            "COMPLETE",
            "UNKNOWN",
        }


def test_get_process_detail_includes_activities_and_edges(
    client: TestClient, db: Session, tmp_path: Path
) -> None:
    org_id = create_organization(client, "proc-detail")
    case_id, run_id = _run_case(db, tmp_path, org_id)
    listed = client.get(
        f"/api/v1/organizations/{org_id}/analysis-cases/{case_id}/processes",
        params={"run_id": str(run_id)},
    ).json()
    assert listed["processes"], "expected at least one discovered process instance"
    process_id = listed["processes"][0]["id"]

    response = client.get(
        f"/api/v1/organizations/{org_id}/analysis-cases/{case_id}/processes/{process_id}"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == process_id
    assert isinstance(body["activities"], list)
    assert isinstance(body["edges"], list)


def test_get_process_not_found_returns_404(client: TestClient, db: Session, tmp_path: Path) -> None:
    org_id = create_organization(client, "proc-404")
    case_id, _ = _run_case(db, tmp_path, org_id)
    response = client.get(
        f"/api/v1/organizations/{org_id}/analysis-cases/{case_id}/processes/{uuid4()}"
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "CANONICAL_PROCESS_NOT_FOUND"


def test_process_graph_and_summary(client: TestClient, db: Session, tmp_path: Path) -> None:
    org_id = create_organization(client, "proc-graph")
    case_id, run_id = _run_case(db, tmp_path, org_id)

    graph_response = client.get(
        f"/api/v1/organizations/{org_id}/analysis-cases/{case_id}/process-graph",
        params={"run_id": str(run_id)},
    )
    assert graph_response.status_code == 200, graph_response.text
    graph = graph_response.json()
    assert isinstance(graph["nodes"], list)
    assert isinstance(graph["edges"], list)
    node_ids = {n["id"] for n in graph["nodes"]}
    for edge in graph["edges"]:
        assert edge["from_activity_id"] in node_ids
        assert edge["to_activity_id"] in node_ids

    summary_response = client.get(
        f"/api/v1/organizations/{org_id}/analysis-cases/{case_id}/process-graph/summary",
        params={"run_id": str(run_id)},
    )
    assert summary_response.status_code == 200, summary_response.text
    summary = summary_response.json()
    assert summary["activity_count"] == len(graph["nodes"])
    assert summary["edge_count"] == len(graph["edges"])


def test_cross_tenant_process_access_returns_404(
    client: TestClient, db: Session, tmp_path: Path
) -> None:
    org_id = create_organization(client, "proc-tenant-a")
    other_org_id = create_organization(client, "proc-tenant-b")
    case_id, run_id = _run_case(db, tmp_path, org_id)
    listed = client.get(
        f"/api/v1/organizations/{org_id}/analysis-cases/{case_id}/processes",
        params={"run_id": str(run_id)},
    ).json()
    assert listed["processes"]
    process_id = listed["processes"][0]["id"]

    response = client.get(
        f"/api/v1/organizations/{other_org_id}/analysis-cases/{case_id}/processes/{process_id}"
    )
    assert response.status_code == 404


def test_unauthenticated_request_is_rejected(
    client: TestClient, db: Session, tmp_path: Path, identity: IdentityState
) -> None:
    org_id = create_organization(client, "proc-unauth")
    case_id, _ = _run_case(db, tmp_path, org_id)
    identity.user_id = None
    response = client.get(f"/api/v1/organizations/{org_id}/analysis-cases/{case_id}/processes")
    assert response.status_code == 401
