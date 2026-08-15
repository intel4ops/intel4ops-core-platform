from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from conftest import IdentityState
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_decision_intelligence_foundation import make_org
from test_p3_08_recovery_workspace import _approve, _finding, _recommendation
from test_recovery_ledger_api import approved_foundation

from app.main import app
from app.models.actions import ActionOutcome, OperationalAction
from app.models.decision_intelligence import DecisionApproval, DecisionRecommendation
from app.models.entities import Finding
from app.models.recovery_ledger import (
    RecoveryExecution,
    RecoveryFinanceVerification,
    RecoveryValueMeasurement,
    VerifiedValueLedgerEntry,
)
from app.services.decision_intelligence_service import decision_approval_service
from app.services.recovery_portfolio_service import RecoveryPortfolioService


def _path(organization_id: UUID | str, **params: object) -> str:
    query = "&".join(f"{key}={value}" for key, value in params.items())
    suffix = f"?{query}" if query else ""
    return f"/api/v1/organizations/{organization_id}/recovery/portfolio{suffix}"


def _approved_recommendation(
    db: Session, organization_id: UUID, actor_id: UUID, suffix: str
) -> tuple[Finding, DecisionRecommendation]:
    finding = _finding(db, organization_id, suffix)
    recommendation = _recommendation(db, organization_id, finding.id, actor_id)
    _approve(db, organization_id, recommendation, actor_id)
    return finding, recommendation


def _verified_chain(
    client: TestClient,
    identity: IdentityState,
    db: Session,
    slug: str,
) -> tuple[UUID, Finding, OperationalAction, dict[str, object]]:
    organization_id_text, _, baseline = approved_foundation(client, slug)
    organization_id = UUID(organization_id_text)
    actor_id = identity.user_id
    assert actor_id is not None
    finding, recommendation = _approved_recommendation(db, organization_id, actor_id, slug.upper())
    action = decision_approval_service.convert_to_action(
        db, organization_id, recommendation.id, actor_id
    )
    action.assigned_user_id = actor_id
    action.assigned_role = "recovery_manager"
    action.due_at = datetime.now(UTC) - timedelta(days=1)
    db.commit()
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
            "idempotency_key": f"{slug}-case",
            "title": "Verified portfolio recovery",
            "description": "Expected, realized, and verified remain distinct.",
        },
    ).json()
    execution = client.post(
        f"/api/v1/organizations/{organization_id}/recovery-cases/{case['id']}/executions",
        json={"action_id": str(action.id), "idempotency_key": f"{slug}-execution"},
    ).json()
    for transition in ("start", "complete"):
        response = client.post(
            f"/api/v1/organizations/{organization_id}/recovery-executions/"
            f"{execution['id']}/{transition}"
        )
        assert response.status_code == 200, response.text
    db.add(
        ActionOutcome(
            organization_id=organization_id,
            action_id=action.id,
            outcome_type="expected",
            avoided_cost=900,
            intervention_cost=100,
            currency_code="USD",
            calculation_method="governed_forecast",
            assumptions=[],
            limitations=[],
        )
    )
    db.commit()
    now = datetime.now(UTC)
    measurement = client.post(
        f"/api/v1/organizations/{organization_id}/recovery-executions/"
        f"{execution['id']}/measurements",
        json={
            "idempotency_key": f"{slug}-measurement",
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
                    "source_identifier": f"INV-{slug}",
                }
            ],
        },
    ).json()
    assert (
        client.post(
            f"/api/v1/organizations/{organization_id}/recovery-measurements/"
            f"{measurement['id']}/submit"
        ).status_code
        == 200
    )
    identity.user_id = uuid4()
    verified = client.post(
        f"/api/v1/organizations/{organization_id}/recovery-measurements/{measurement['id']}/verify",
        json={
            "idempotency_key": f"{slug}-verify",
            "verified_amount": "275",
            "currency_code": "USD",
            "rationale": "Independent finance verification",
        },
    )
    assert verified.status_code == 201, verified.text
    return organization_id, finding, action, case


def test_portfolio_requires_authentication_and_membership(
    client: TestClient, identity: IdentityState, db: Session
) -> None:
    identity.user_id = None
    assert client.get(_path(uuid4())).status_code == 401
    organization_id, _ = make_org(db, "p309-membership")
    identity.user_id = uuid4()
    identity.is_platform_admin = False
    assert client.get(_path(organization_id)).status_code in {403, 404}


def test_empty_portfolio_is_honest(client: TestClient, db: Session) -> None:
    organization_id, _ = make_org(db, "p309-empty")
    body = client.get(_path(organization_id)).json()
    assert body["items"] == []
    assert body["pagination"] == {"page": 1, "page_size": 50, "total": 0}
    assert body["summary"]["value_by_currency"] == []


def test_approved_without_action_and_action_without_recovery_are_distinct(
    client: TestClient, db: Session
) -> None:
    organization_id, actor_id = make_org(db, "p309-stages")
    _, first = _approved_recommendation(db, organization_id, actor_id, "APPROVED")
    _, second = _approved_recommendation(db, organization_id, actor_id, "ACTION")
    action = decision_approval_service.convert_to_action(db, organization_id, second.id, actor_id)

    body = client.get(_path(organization_id, page_size=1)).json()
    assert body["pagination"]["total"] == 2
    assert len(body["items"]) == 1
    all_items = client.get(_path(organization_id, page_size=10)).json()["items"]
    stages = {item["recommendation_id"]: item["stage"] for item in all_items}
    assert stages[str(first.id)] == "approved_no_action"
    assert stages[str(second.id)] == "action_active"
    assert (
        next(item for item in all_items if item["action_id"] == str(action.id))["realized_value"]
        is None
    )


def test_verified_portfolio_values_filters_overdue_and_currency_groups(
    client: TestClient, identity: IdentityState, db: Session
) -> None:
    organization_id, finding, action, case = _verified_chain(client, identity, db, "p309-verified")
    actor_id = identity.user_id
    assert actor_id is not None
    _, cad_recommendation = _approved_recommendation(db, organization_id, actor_id, "CAD-FALLBACK")
    cad_action = decision_approval_service.convert_to_action(
        db, organization_id, cad_recommendation.id, actor_id
    )
    cad_action.expected_avoided_cost = Decimal("500")
    cad_action.currency_code = "CAD"
    cad_action.assigned_role = "operator"
    db.commit()

    body = client.get(_path(organization_id, page_size=10)).json()
    verified = next(item for item in body["items"] if item["finding_id"] == str(finding.id))
    assert verified["stage"] == "verified"
    assert verified["expected_value"] != verified["realized_value"]
    assert verified["realized_value"] == "300.000000000000"
    assert verified["verified_value"] == "275.000000000000"
    assert verified["overdue"] is True
    assert verified["assigned_role"] == "recovery_manager"
    totals = {item["currency_code"]: item for item in body["summary"]["value_by_currency"]}
    assert set(totals) == {"CAD", "USD"}
    assert totals["USD"]["expected_value"] != (
        totals["USD"]["realized_value"] + totals["USD"]["verified_value"]
    )
    assert totals["CAD"]["expected_value"] == "500.000000000000"
    assert totals["CAD"]["realized_value"] == "0"
    assert body["summary"]["overdue_count"] == 1
    assert (
        client.get(_path(organization_id, overdue_only="true")).json()["pagination"]["total"] == 1
    )
    assert client.get(_path(organization_id, owner_role="operator")).json()["items"][0][
        "action_id"
    ] == str(cad_action.id)
    assert client.get(_path(organization_id, currency="CAD")).json()["pagination"]["total"] == 1
    assert (
        client.get(_path(organization_id, finding_id=finding.id)).json()["items"][0][
            "recovery_case_id"
        ]
        == case["id"]
    )
    foreign_id, _ = make_org(db, "p309-foreign")
    assert client.get(_path(foreign_id, action_id=action.id)).json()["items"] == []


def test_stage_mapping_never_collapses_lifecycle_states() -> None:
    service = RecoveryPortfolioService()
    recommendation = DecisionRecommendation()
    approved = DecisionApproval(decision="approve")
    action = OperationalAction(status="completed")
    execution = RecoveryExecution(status="in_progress")
    outcome = ActionOutcome()
    submitted = RecoveryValueMeasurement(status="submitted")
    rejected = RecoveryFinanceVerification(decision="rejected")
    ledger_entry = VerifiedValueLedgerEntry()
    assert service._stage(recommendation, approved, None, None, None, None, None, []) == (
        "approved_no_action"
    )
    assert service._stage(recommendation, approved, action, None, None, None, None, []) == (
        "action_active"
    )
    assert service._stage(recommendation, approved, action, execution, None, None, None, []) == (
        "execution_active"
    )
    assert service._stage(recommendation, approved, action, execution, outcome, None, None, []) == (
        "outcome_recorded"
    )
    assert (
        service._stage(recommendation, approved, action, execution, outcome, submitted, None, [])
        == "verification_pending"
    )
    assert (
        service._stage(
            recommendation, approved, action, execution, outcome, submitted, rejected, []
        )
        == "verification_attention"
    )
    assert (
        service._stage(
            recommendation,
            approved,
            action,
            execution,
            outcome,
            submitted,
            rejected,
            [ledger_entry],
        )
        == "verified"
    )


def test_openapi_registers_portfolio_query_contract() -> None:
    path = "/api/v1/organizations/{organization_id}/recovery/portfolio"
    operation = app.openapi()["paths"][path]["get"]
    names = {parameter["name"] for parameter in operation["parameters"]}
    assert {"page", "page_size", "owner_role", "currency", "overdue_only"} <= names
    ids = [
        value["operationId"]
        for routes in app.openapi()["paths"].values()
        for value in routes.values()
        if isinstance(value, dict) and "operationId" in value
    ]
    assert len(ids) == len(set(ids))
