from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from conftest import IdentityState
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_decision_intelligence_foundation import add_graph, make_org
from test_recovery_ledger_api import approved_foundation

from app.main import app
from app.models.actions import ActionEvidence, ActionOutcome
from app.models.decision_intelligence import (
    DecisionExecution,
    DecisionScenarioInput,
    DecisionSolution,
)
from app.models.entities import Finding
from app.models.recovery_ledger import RecoveryFinanceVerification
from app.schemas.decision_intelligence import DecisionApprovalCreate
from app.services.decision_intelligence_service import decision_approval_service


def _path(organization_id: UUID | str, finding_id: UUID) -> str:
    return f"/api/v1/organizations/{organization_id}/findings/{finding_id}/recovery-workspace"


def _finding(db: Session, organization_id: UUID, suffix: str) -> Finding:
    row = Finding(
        organization_id=organization_id,
        rule_id=f"P3.08-{suffix}",
        title="Governed recovery finding",
        summary="Finding available for recovery.",
        domain="operations",
        severity="high",
        priority=2,
        exposure_low=0,
        exposure_high=0,
        currency="USD",
        confidence_score=0,
        status="published",
        governance_tier="GOVERNED",
        finding_code=f"P308-{suffix}",
        finding_type="risk",
        detected_at=datetime.now(UTC),
    )
    db.add(row)
    db.commit()
    return row


def _recommendation(db: Session, organization_id: UUID, finding_id: UUID, actor_id: UUID) -> object:
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
            source_fingerprint="8" * 64,
            input_payload={},
            validation_flags=[],
        )
    )
    db.commit()
    return recommendation


def _approve(db: Session, organization_id: UUID, recommendation: object, actor_id: UUID) -> None:
    decision_approval_service.decide(
        db,
        organization_id,
        recommendation.id,
        DecisionApprovalCreate(
            decision="approve",
            rationale="Approved for governed recovery",
            idempotency_key=f"p308-approve-{recommendation.id}",
        ),
        actor_id,
        "organization_admin",
    )


def test_recovery_workspace_requires_authentication(
    client: TestClient, identity: IdentityState
) -> None:
    identity.user_id = None
    assert client.get(_path(uuid4(), uuid4())).status_code == 401


def test_empty_and_approved_without_action_are_honest(client: TestClient, db: Session) -> None:
    organization_id, actor_id = make_org(db, "p308-empty")
    finding = _finding(db, organization_id, "EMPTY")
    empty = client.get(_path(organization_id, finding.id))
    assert empty.status_code == 200
    assert empty.json()["recommendation"] is None
    assert empty.json()["action"] is None
    assert empty.json()["measurements"] == []

    recommendation = _recommendation(db, organization_id, finding.id, actor_id)
    _approve(db, organization_id, recommendation, actor_id)
    approved = client.get(_path(organization_id, finding.id)).json()
    assert approved["approval"]["decision"] == "approve"
    assert approved["action"] is None
    assert approved["recovery_execution"] is None


def test_action_outcome_evidence_and_history_are_scoped(client: TestClient, db: Session) -> None:
    organization_id, actor_id = make_org(db, "p308-action")
    finding = _finding(db, organization_id, "ACTION")
    recommendation = _recommendation(db, organization_id, finding.id, actor_id)
    _approve(db, organization_id, recommendation, actor_id)
    action = decision_approval_service.convert_to_action(
        db, organization_id, recommendation.id, actor_id
    )
    db.add_all(
        [
            ActionEvidence(
                organization_id=organization_id,
                action_id=action.id,
                lifecycle_stage="execution",
                evidence_type="work_order",
                source_type="external_system",
                source_identifier="WO-308",
                actor_user_id=actor_id,
                metadata_json={"governed": True},
            ),
            ActionOutcome(
                organization_id=organization_id,
                action_id=action.id,
                outcome_type="expected",
                avoided_cost=1000,
                intervention_cost=100,
                currency_code="USD",
                calculation_method="governed_forecast",
                assumptions=[],
                limitations=[],
            ),
        ]
    )
    db.commit()

    body = client.get(_path(organization_id, finding.id)).json()
    assert body["action"]["id"] == str(action.id)
    assert body["action"]["status"] == "approved"
    assert body["action_evidence"][0]["source_identifier"] == "WO-308"
    assert body["action_outcomes"][0]["outcome_type"] == "expected"
    assert body["recovery_case"] is None
    assert all(item["entity_id"] == str(recommendation.id) for item in body.get("history", []))


def test_full_recovery_value_verification_and_latest_review_are_discovered(
    client: TestClient, identity: IdentityState, db: Session
) -> None:
    organization_id_text, _, baseline = approved_foundation(client, "p308-full")
    organization_id = UUID(organization_id_text)
    actor_id = identity.user_id
    assert actor_id is not None
    finding = _finding(db, organization_id, "FULL")
    recommendation = _recommendation(db, organization_id, finding.id, actor_id)
    _approve(db, organization_id, recommendation, actor_id)
    action = decision_approval_service.convert_to_action(
        db, organization_id, recommendation.id, actor_id
    )
    linked = client.post(
        f"/api/v1/organizations/{organization_id}/recovery-opportunities/"
        f"{baseline['opportunity_id']}/actions",
        json={"action_id": str(action.id), "relationship_type": "approved_recovery"},
    )
    assert linked.status_code == 201, linked.text
    case = client.post(
        f"/api/v1/organizations/{organization_id}/recovery-cases",
        json={
            "opportunity_id": baseline["opportunity_id"],
            "baseline_id": baseline["id"],
            "idempotency_key": "p308-case",
            "title": "P3.08 governed recovery",
            "description": "Measure and verify separately.",
        },
    ).json()
    execution = client.post(
        f"/api/v1/organizations/{organization_id}/recovery-cases/{case['id']}/executions",
        json={"action_id": str(action.id), "idempotency_key": "p308-execution"},
    ).json()
    for transition in ("start", "complete"):
        response = client.post(
            f"/api/v1/organizations/{organization_id}/recovery-executions/"
            f"{execution['id']}/{transition}"
        )
        assert response.status_code == 200, response.text
    now = datetime.now(UTC)
    measurement = client.post(
        f"/api/v1/organizations/{organization_id}/recovery-executions/"
        f"{execution['id']}/measurements",
        json={
            "idempotency_key": "p308-measurement",
            "category": "cost_reduction",
            "baseline_amount": "1000",
            "actual_amount": "700",
            "currency_code": "USD",
            "measurement_start": (now - timedelta(days=1)).isoformat(),
            "measurement_end": now.isoformat(),
            "methodology": "period_cost_comparison",
            "calculation_inputs": {},
            "evidence": [
                {
                    "evidence_type": "invoice",
                    "source_type": "external_system",
                    "source_identifier": "INV-308",
                }
            ],
        },
    ).json()
    assert (
        client.post(
            f"/api/v1/organizations/{organization_id}/recovery-measurements/{measurement['id']}/submit"
        ).status_code
        == 200
    )
    older = RecoveryFinanceVerification(
        organization_id=organization_id,
        measurement_id=UUID(measurement["id"]),
        idempotency_key="p308-older-review",
        decision="needs_information",
        verified_amount=0,
        currency_code="USD",
        rationale="Older review",
        reviewer_user_id=uuid4(),
        reviewed_at=now - timedelta(seconds=1),
    )
    db.add(older)
    db.commit()
    identity.user_id = uuid4()
    verified = client.post(
        f"/api/v1/organizations/{organization_id}/recovery-measurements/{measurement['id']}/verify",
        json={
            "idempotency_key": "p308-verified",
            "verified_amount": "275",
            "currency_code": "USD",
            "rationale": "Independent verification",
        },
    )
    assert verified.status_code == 201, verified.text

    body = client.get(_path(organization_id, finding.id)).json()
    assert body["recovery_case"]["expected_value"] != body["measurements"][0]["realized_value"]
    assert body["measurements"][0]["realized_value"] == "300.000000000000"
    assert body["latest_verification"]["decision"] == "approved"
    assert body["latest_verification"]["verified_amount"] == "275.000000000000"
    assert body["verified_ledger"][0]["amount"] == "275.000000000000"
    assert body["measurement_evidence"][0]["source_identifier"] == "INV-308"
    assert body["recovery_history"]


def test_cross_tenant_is_controlled_and_openapi_is_registered(
    client: TestClient, db: Session
) -> None:
    first_id, _ = make_org(db, "p308-tenant-first")
    second_id, _ = make_org(db, "p308-tenant-second")
    finding = _finding(db, first_id, "TENANT")
    assert client.get(_path(second_id, finding.id)).status_code == 404
    assert (
        "/api/v1/organizations/{organization_id}/findings/{finding_id}/recovery-workspace"
        in app.openapi()["paths"]
    )
