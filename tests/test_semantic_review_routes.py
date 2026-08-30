"""P3.xxE.1A: API-level tests for app/api/semantic_review_routes.py --
auth, review queue, submit review, history, effective-for-run, cross-
tenant scoping, and deterministic error payloads. Uses the shared
`client`/`identity`/`db` fixtures from tests/conftest.py."""

from pathlib import Path
from uuid import UUID, uuid4

from conftest import IdentityState
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.semantic import SemanticInterpretationDecision
from app.services.analysis_case_orchestration_service import analysis_case_orchestration_service
from app.services.analysis_case_service import AnalysisCaseService, UploadedFile
from app.storage.local_storage import LocalFileStorage

MAINT_CSV = (
    b"asset_id,failure_code,downtime_hours,repair_cost,event_date\n"
    b"V1,brake,4,10000,2026-08-01T08:00:00\n"
    b"V1,brake,5,11000,2026-08-05T08:00:00\n"
    b"V1,brake,6,12000,2026-08-10T08:00:00\n"
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
        db, org_id, case.id, [UploadedFile("maintenance_events.csv", MAINT_CSV)], actor
    )
    run = analysis_case_orchestration_service.start_run(db, org_id, case.id, actor)
    analysis_case_orchestration_service.execute(db, service.storage, org_id, case.id, run.id, actor)
    return case.id, run.id


def _force_status(db: Session, decision_id: UUID, status: str, confidence: float) -> None:
    db.execute(
        update(SemanticInterpretationDecision)
        .where(SemanticInterpretationDecision.id == decision_id)
        .values(status=status, confidence=confidence)
    )
    db.commit()


def _decision_id(db: Session, run_id: UUID, source_field: str) -> UUID:
    decision = db.scalar(
        select(SemanticInterpretationDecision).where(
            SemanticInterpretationDecision.run_id == run_id,
            SemanticInterpretationDecision.source_field == source_field,
        )
    )
    assert decision is not None
    return decision.id


def test_review_queue_lists_pending_items(client: TestClient, db: Session, tmp_path: Path) -> None:
    org_id = create_organization(client, "sr-queue")
    case_id, run_id = _run_case(db, tmp_path, org_id)
    decision_id = _decision_id(db, run_id, "asset_id")
    _force_status(db, decision_id, "review_required", 0.5)

    response = client.get(
        f"/api/v1/organizations/{org_id}/analysis-cases/{case_id}/semantic/review-queue",
        params={"run_id": str(run_id)},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    field_names = {item["source_field"] for item in body["items"]}
    assert "asset_id" in field_names
    matching = next(item for item in body["items"] if item["source_field"] == "asset_id")
    assert matching["group"] == "pending_review"
    assert matching["current_version"] is None


def test_submit_review_confirm_then_effective_endpoint_reflects_it(
    client: TestClient, db: Session, tmp_path: Path
) -> None:
    org_id = create_organization(client, "sr-confirm-api")
    case_id, run_id = _run_case(db, tmp_path, org_id)
    decision_id = _decision_id(db, run_id, "asset_id")
    _force_status(db, decision_id, "review_required", 0.5)

    review_path = (
        f"/api/v1/organizations/{org_id}/analysis-cases/{case_id}"
        f"/semantic/decisions/{decision_id}/review"
    )
    response = client.post(
        review_path,
        json={"action": "confirm", "expected_version": 0},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["version"]["effective_status"] == "human_confirmed"
    assert body["effective_decision"]["human_validated"] is True

    effective = client.get(
        f"/api/v1/organizations/{org_id}/analysis-cases/{case_id}/semantic/effective",
        params={"run_id": str(run_id)},
    )
    assert effective.status_code == 200, effective.text
    fields = {f["source_field"]: f for f in effective.json()["fields"]}
    assert fields["asset_id"]["effective_decision"]["human_validated"] is True


def test_submit_review_stale_version_returns_409(
    client: TestClient, db: Session, tmp_path: Path
) -> None:
    org_id = create_organization(client, "sr-conflict-api")
    case_id, run_id = _run_case(db, tmp_path, org_id)
    decision_id = _decision_id(db, run_id, "asset_id")
    _force_status(db, decision_id, "review_required", 0.5)

    review_path = (
        f"/api/v1/organizations/{org_id}/analysis-cases/{case_id}"
        f"/semantic/decisions/{decision_id}/review"
    )
    first = client.post(review_path, json={"action": "reject", "expected_version": 0})
    assert first.status_code == 201, first.text

    stale = client.post(
        review_path,
        json={"action": "correct", "corrected_concept": "asset_id", "expected_version": 0},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "SEMANTIC_REVIEW_VERSION_CONFLICT"


def test_submit_review_unknown_concept_returns_400(
    client: TestClient, db: Session, tmp_path: Path
) -> None:
    org_id = create_organization(client, "sr-bad-concept-api")
    case_id, run_id = _run_case(db, tmp_path, org_id)
    decision_id = _decision_id(db, run_id, "asset_id")
    _force_status(db, decision_id, "review_required", 0.5)

    response = client.post(
        f"/api/v1/organizations/{org_id}/analysis-cases/{case_id}"
        f"/semantic/decisions/{decision_id}/review",
        json={
            "action": "correct",
            "corrected_concept": "not_a_real_concept",
            "expected_version": 0,
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "SEMANTIC_REVIEW_INVALID_CONCEPT"


def test_review_history_shows_machine_proposal_then_review_then_version(
    client: TestClient, db: Session, tmp_path: Path
) -> None:
    org_id = create_organization(client, "sr-history-api")
    case_id, run_id = _run_case(db, tmp_path, org_id)
    decision_id = _decision_id(db, run_id, "asset_id")
    _force_status(db, decision_id, "review_required", 0.5)

    review_path = (
        f"/api/v1/organizations/{org_id}/analysis-cases/{case_id}"
        f"/semantic/decisions/{decision_id}/review"
    )
    client.post(review_path, json={"action": "reject", "expected_version": 0})
    client.post(
        review_path,
        json={"action": "correct", "corrected_concept": "asset_id", "expected_version": 1},
    )

    history = client.get(
        f"/api/v1/organizations/{org_id}/analysis-cases/{case_id}"
        f"/semantic/decisions/{decision_id}/history"
    )
    assert history.status_code == 200, history.text
    body = history.json()
    assert body["machine_proposal"]["source_field"] == "asset_id"
    assert [e["version"]["effective_status"] for e in body["entries"]] == [
        "human_rejected",
        "human_corrected",
    ]


def test_cross_tenant_decision_access_returns_not_found(
    client: TestClient, db: Session, tmp_path: Path
) -> None:
    org_id = create_organization(client, "sr-tenant-a")
    other_org_id = create_organization(client, "sr-tenant-b")
    case_id, run_id = _run_case(db, tmp_path, org_id)
    decision_id = _decision_id(db, run_id, "asset_id")

    response = client.get(
        f"/api/v1/organizations/{other_org_id}/analysis-cases/{case_id}"
        f"/semantic/decisions/{decision_id}/review"
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "SEMANTIC_DECISION_NOT_FOUND"


def test_unauthorized_reviewer_without_membership_gets_403(
    client: TestClient, db: Session, tmp_path: Path, identity: IdentityState
) -> None:
    org_id = create_organization(client, "sr-unauthorized")
    case_id, run_id = _run_case(db, tmp_path, org_id)

    identity.is_platform_admin = False
    identity.user_id = uuid4()  # a user with no membership in org_id at all
    response = client.get(
        f"/api/v1/organizations/{org_id}/analysis-cases/{case_id}/semantic/review-queue"
    )
    assert response.status_code == 403


def test_unauthenticated_request_is_rejected(
    client: TestClient, db: Session, tmp_path: Path, identity: IdentityState
) -> None:
    org_id = create_organization(client, "sr-unauth-req")
    case_id, _ = _run_case(db, tmp_path, org_id)
    identity.user_id = None
    response = client.get(
        f"/api/v1/organizations/{org_id}/analysis-cases/{case_id}/semantic/review-queue"
    )
    assert response.status_code == 401


def test_queue_default_view_excludes_resolved_but_group_all_returns_it(
    client: TestClient, db: Session, tmp_path: Path
) -> None:
    org_id = create_organization(client, "sr-queue-groups")
    case_id, run_id = _run_case(db, tmp_path, org_id)
    decision_id = _decision_id(db, run_id, "asset_id")
    _force_status(db, decision_id, "review_required", 0.5)

    client.post(
        f"/api/v1/organizations/{org_id}/analysis-cases/{case_id}"
        f"/semantic/decisions/{decision_id}/review",
        json={"action": "confirm", "expected_version": 0},
    )

    default_view = client.get(
        f"/api/v1/organizations/{org_id}/analysis-cases/{case_id}/semantic/review-queue",
        params={"run_id": str(run_id)},
    )
    assert decision_id.hex not in [
        item["decision_id"].replace("-", "") for item in default_view.json()["items"]
    ]

    all_view = client.get(
        f"/api/v1/organizations/{org_id}/analysis-cases/{case_id}/semantic/review-queue",
        params={"run_id": str(run_id), "group": "all"},
    )
    resolved_ids = [item["decision_id"] for item in all_view.json()["items"]]
    assert str(decision_id) in resolved_ids
