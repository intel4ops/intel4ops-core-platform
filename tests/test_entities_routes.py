"""P3.xxE.3: API-level tests for app/api/entities_routes.py -- read-only,
tenant-scoped, and never blends in the legacy AnalysisCaseEntityLink
system (plan review correction 3)."""

from pathlib import Path
from uuid import UUID, uuid4

from conftest import IdentityState
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.services.analysis_case_orchestration_service import analysis_case_orchestration_service
from app.services.analysis_case_service import AnalysisCaseService, UploadedFile
from app.storage.local_storage import LocalFileStorage

EVENTS_CSV = (
    b"asset_id,work_order_id,event_date\n"
    + b"\n".join(f"A-{(i % 4) + 1},WO-{i + 1},2026-01-{i + 1:02d}".encode() for i in range(12))
    + b"\n"
)
WORK_ORDERS_CSV = (
    b"work_order_id,asset_id,technician_id\n"
    + b"\n".join(f"WO-{i + 1},A-{(i % 4) + 1},T-{i % 3}".encode() for i in range(12))
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
            UploadedFile("events.csv", EVENTS_CSV),
            UploadedFile("work_orders.csv", WORK_ORDERS_CSV),
        ],
        actor,
    )
    run = analysis_case_orchestration_service.start_run(db, org_id, case.id, actor)
    analysis_case_orchestration_service.execute(db, service.storage, org_id, case.id, run.id, actor)
    return case.id, run.id


def test_list_entities_returns_resolved_entities(
    client: TestClient, db: Session, tmp_path: Path
) -> None:
    org_id = create_organization(client, "ent-list")
    case_id, run_id = _run_case(db, tmp_path, org_id)

    response = client.get(
        f"/api/v1/organizations/{org_id}/analysis-cases/{case_id}/entities",
        params={"run_id": str(run_id)},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["run_id"] == str(run_id)
    entity_types = {e["entity_type"] for e in body["entities"]}
    assert "ASSET" in entity_types
    assert "WORK_ORDER" in entity_types
    for entity in body["entities"]:
        assert 0.0 <= entity["entity_type_confidence"] <= 1.0
        assert 0.0 <= entity["entity_identity_confidence"] <= 1.0


def test_get_entity_detail_includes_observations(
    client: TestClient, db: Session, tmp_path: Path
) -> None:
    org_id = create_organization(client, "ent-detail")
    case_id, run_id = _run_case(db, tmp_path, org_id)
    listed = client.get(
        f"/api/v1/organizations/{org_id}/analysis-cases/{case_id}/entities",
        params={"run_id": str(run_id)},
    ).json()
    entity_id = listed["entities"][0]["id"]

    response = client.get(
        f"/api/v1/organizations/{org_id}/analysis-cases/{case_id}/entities/{entity_id}"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == entity_id
    assert isinstance(body["observations"], list)
    assert len(body["observations"]) >= 1


def test_get_entity_not_found_returns_404(client: TestClient, db: Session, tmp_path: Path) -> None:
    org_id = create_organization(client, "ent-404")
    case_id, _ = _run_case(db, tmp_path, org_id)
    response = client.get(
        f"/api/v1/organizations/{org_id}/analysis-cases/{case_id}/entities/{uuid4()}"
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "CANONICAL_ENTITY_NOT_FOUND"


def test_list_relationships_and_entity_graph(
    client: TestClient, db: Session, tmp_path: Path
) -> None:
    org_id = create_organization(client, "ent-rel")
    case_id, run_id = _run_case(db, tmp_path, org_id)

    rel_response = client.get(
        f"/api/v1/organizations/{org_id}/analysis-cases/{case_id}/relationships",
        params={"run_id": str(run_id)},
    )
    assert rel_response.status_code == 200, rel_response.text
    relationships = rel_response.json()["relationships"]
    assert relationships
    for r in relationships:
        assert r["relationship_type"] in {
            "REFERENCES",
            "BELONGS_TO",
            "HAS",
            "USES",
            "GENERATES",
            "PERFORMED_BY",
            "LOCATED_AT",
            "ASSOCIATED_WITH",
        }

    graph_response = client.get(
        f"/api/v1/organizations/{org_id}/analysis-cases/{case_id}/entity-graph",
        params={"run_id": str(run_id)},
    )
    assert graph_response.status_code == 200, graph_response.text
    graph = graph_response.json()
    assert len(graph["nodes"]) >= 2
    assert len(graph["edges"]) >= 1
    node_ids = {n["id"] for n in graph["nodes"]}
    for edge in graph["edges"]:
        assert edge["left_entity_id"] in node_ids
        assert edge["right_entity_id"] in node_ids


def test_cross_tenant_entity_access_returns_404(
    client: TestClient, db: Session, tmp_path: Path
) -> None:
    org_id = create_organization(client, "ent-tenant-a")
    other_org_id = create_organization(client, "ent-tenant-b")
    case_id, run_id = _run_case(db, tmp_path, org_id)
    listed = client.get(
        f"/api/v1/organizations/{org_id}/analysis-cases/{case_id}/entities",
        params={"run_id": str(run_id)},
    ).json()
    entity_id = listed["entities"][0]["id"]

    response = client.get(
        f"/api/v1/organizations/{other_org_id}/analysis-cases/{case_id}/entities/{entity_id}"
    )
    assert response.status_code == 404


def test_unauthenticated_request_is_rejected(
    client: TestClient, db: Session, tmp_path: Path, identity: IdentityState
) -> None:
    org_id = create_organization(client, "ent-unauth")
    case_id, _ = _run_case(db, tmp_path, org_id)
    identity.user_id = None
    response = client.get(f"/api/v1/organizations/{org_id}/analysis-cases/{case_id}/entities")
    assert response.status_code == 401
