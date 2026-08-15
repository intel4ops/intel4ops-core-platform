from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from conftest import IdentityState
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_decision_intelligence_foundation import add_graph, make_org

from app.main import app
from app.models.decision_intelligence import (
    DecisionApproval,
    DecisionAuditEvent,
    DecisionExecution,
    DecisionRecommendation,
    DecisionScenarioInput,
    DecisionSolution,
)
from app.models.entities import Finding


def _finding(db: Session, organization_id: UUID, suffix: str) -> Finding:
    item = Finding(
        organization_id=organization_id,
        rule_id=f"P3.07A-{suffix}",
        title="Governed finding",
        summary="Finding available for decision review.",
        domain="operations",
        severity="high",
        priority=2,
        exposure_low=0,
        exposure_high=0,
        currency="USD",
        confidence_score=0,
        status="published",
        governance_tier="GOVERNED",
        finding_code=f"FND-{suffix}",
        finding_type="risk",
        detected_at=datetime.now(UTC),
    )
    db.add(item)
    db.commit()
    return item


def _link(
    db: Session, organization_id: UUID, finding_id: UUID, actor_id: UUID
) -> DecisionRecommendation:
    recommendation, _ = add_graph(db, organization_id, actor_id)
    scenario_id = db.scalar(
        select(DecisionExecution.scenario_id)
        .join(DecisionSolution, DecisionSolution.execution_id == DecisionExecution.id)
        .where(DecisionSolution.id == recommendation.solution_id)
    )
    assert scenario_id is not None
    db.add(
        DecisionScenarioInput(
            organization_id=organization_id,
            scenario_id=scenario_id,
            input_kind="finding",
            source_id=finding_id,
            source_fingerprint="1" * 64,
            input_payload={},
            validation_flags=[],
        )
    )
    db.commit()
    return recommendation


def _path(organization_id: UUID, finding_id: UUID) -> str:
    return f"/api/v1/organizations/{organization_id}/findings/{finding_id}/decision-workspace"


def test_decision_workspace_requires_authentication(
    client: TestClient, identity: IdentityState
) -> None:
    identity.user_id = None
    assert client.get(_path(uuid4(), uuid4())).status_code == 401


def test_existing_finding_without_decision_returns_honest_empty_workspace(
    client: TestClient, db: Session
) -> None:
    organization_id, _ = make_org(db, "p307a-empty")
    finding = _finding(db, organization_id, "EMPTY")

    response = client.get(_path(organization_id, finding.id))

    assert response.status_code == 200
    assert response.json() == {
        "finding_id": str(finding.id),
        "recommendation": None,
        "approval": None,
        "history": [],
    }


def test_workspace_discovers_tenant_chain_latest_review_and_scoped_history(
    client: TestClient, db: Session
) -> None:
    organization_id, actor_id = make_org(db, "p307a-linked")
    finding = _finding(db, organization_id, "LINKED")
    recommendation = _link(db, organization_id, finding.id, actor_id)
    now = datetime.now(UTC)
    older = DecisionApproval(
        organization_id=organization_id,
        recommendation_id=recommendation.id,
        decision="approve",
        rationale="Initially approved",
        reviewer_user_id=actor_id,
        reviewer_role="organization_admin",
        idempotency_key="p307a-approval-old",
        decided_at=now,
    )
    latest_actor = uuid4()
    latest = DecisionApproval(
        organization_id=organization_id,
        recommendation_id=recommendation.id,
        decision="defer",
        rationale="Await updated evidence",
        reviewer_user_id=latest_actor,
        reviewer_role="organization_admin",
        idempotency_key="p307a-approval-latest",
        decided_at=now + timedelta(seconds=1),
    )
    unrelated = DecisionAuditEvent(
        organization_id=organization_id,
        event_type="unrelated",
        entity_type="decision_recommendation",
        entity_id=uuid4(),
        actor_user_id=actor_id,
        actor_role="analyst",
        summary="Must not leak",
        event_metadata={"scope": "other"},
        idempotency_key="p307a-history-unrelated",
        occurred_at=now,
    )
    first_history = DecisionAuditEvent(
        organization_id=organization_id,
        event_type="recommendation_created",
        entity_type="decision_recommendation",
        entity_id=recommendation.id,
        actor_user_id=actor_id,
        actor_role="analyst",
        summary="Recommendation created",
        event_metadata={"source": "governed"},
        idempotency_key="p307a-history-first",
        occurred_at=now,
    )
    latest_history = DecisionAuditEvent(
        organization_id=organization_id,
        event_type="recommendation_decided",
        entity_type="decision_recommendation",
        entity_id=recommendation.id,
        actor_user_id=latest_actor,
        actor_role="organization_admin",
        summary="Recommendation decision: defer",
        event_metadata={"decision": "defer"},
        idempotency_key="p307a-history-latest",
        occurred_at=now + timedelta(seconds=1),
    )
    db.add_all([older, latest, unrelated, latest_history, first_history])
    db.flush()
    recommendation.approved_by_approval_id = older.id
    db.commit()

    response = client.get(_path(organization_id, finding.id))

    assert response.status_code == 200
    body = response.json()
    assert body["recommendation"]["id"] == str(recommendation.id)
    assert body["recommendation"]["created_by_user_id"] == str(actor_id)
    assert {key: value for key, value in body["approval"].items() if key != "decided_at"} == {
        "id": str(latest.id),
        "organization_id": str(organization_id),
        "recommendation_id": str(recommendation.id),
        "decision": "defer",
        "rationale": "Await updated evidence",
        "reviewer_user_id": str(latest_actor),
        "reviewer_role": "organization_admin",
    }
    assert body["approval"]["decided_at"] == latest.decided_at.isoformat().replace("+00:00", "")
    assert [item["event_type"] for item in body["history"]] == [
        "recommendation_created",
        "recommendation_decided",
    ]
    assert body["history"][0]["actor_role"] == "analyst"
    assert body["history"][0]["event_metadata"] == {"source": "governed"}
    assert body["history"][1]["actor_user_id"] == str(latest_actor)


def test_cross_tenant_finding_and_decision_chain_never_leak(
    client: TestClient, db: Session
) -> None:
    first_id, first_actor = make_org(db, "p307a-tenant-first")
    second_id, second_actor = make_org(db, "p307a-tenant-second")
    first_finding = _finding(db, first_id, "FIRST")
    second_finding = _finding(db, second_id, "SECOND")

    assert client.get(_path(first_id, second_finding.id)).status_code == 404

    _link(db, second_id, first_finding.id, second_actor)
    response = client.get(_path(first_id, first_finding.id))
    assert response.status_code == 200
    assert response.json()["recommendation"] is None

    first_recommendation = _link(db, first_id, first_finding.id, first_actor)
    response = client.get(_path(first_id, first_finding.id))
    assert response.json()["recommendation"]["id"] == str(first_recommendation.id)


def test_generated_openapi_contains_decision_workspace_endpoint() -> None:
    assert (
        "/api/v1/organizations/{organization_id}/findings/{finding_id}/decision-workspace"
        in app.openapi()["paths"]
    )
