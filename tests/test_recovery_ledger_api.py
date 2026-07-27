from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from conftest import IdentityState
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_action_api import action_payload, transition
from test_economics_api import (
    calculate_and_prioritize,
    decide,
    opportunity,
    organization,
    scenario,
)

from app.models.recovery_ledger import VerifiedValueLedgerEntry


def approved_foundation(client: TestClient, slug: str) -> tuple[str, dict, dict]:
    organization_id = organization(client, slug)
    economic_opportunity = opportunity(client, organization_id, f"{slug}:opportunity")
    action_response = client.post(
        f"/api/v1/organizations/{organization_id}/actions",
        json=action_payload(),
    )
    assert action_response.status_code == 201, action_response.text
    action = action_response.json()
    linked = client.post(
        f"/api/v1/organizations/{organization_id}/recovery-opportunities/"
        f"{economic_opportunity['id']}/actions",
        json={"action_id": action["id"], "relationship_type": "approved_recovery"},
    )
    assert linked.status_code == 201, linked.text
    economic_scenario = scenario(client, organization_id, str(economic_opportunity["id"]))
    _, priority = calculate_and_prioritize(
        client,
        organization_id,
        str(economic_opportunity["id"]),
        str(economic_scenario["id"]),
    )
    decide(client, organization_id, str(economic_opportunity["id"]), "under_review")
    decide(
        client,
        organization_id,
        str(economic_opportunity["id"]),
        "economically_qualified",
        scenario_id=str(economic_scenario["id"]),
        prioritization_id=str(priority["id"]),
    )
    approved = decide(
        client,
        organization_id,
        str(economic_opportunity["id"]),
        "approved_for_action",
        scenario_id=str(economic_scenario["id"]),
        prioritization_id=str(priority["id"]),
    )
    for status in ("pending_approval", "approved"):
        transition(client, organization_id, str(action["id"]), status)
    baseline = approved["baseline"]
    assert baseline["version"] == 1
    return organization_id, action, baseline


def test_recovery_execution_verification_and_append_only_ledger(
    client: TestClient, identity: IdentityState, db: Session
) -> None:
    organization_id, action, baseline = approved_foundation(client, "verified-value")
    case_response = client.post(
        f"/api/v1/organizations/{organization_id}/recovery-cases",
        json={
            "opportunity_id": baseline["opportunity_id"],
            "baseline_id": baseline["id"],
            "idempotency_key": "case:one",
            "title": "Recover downtime value",
            "description": "Govern execution and finance verification.",
        },
    )
    assert case_response.status_code == 201, case_response.text
    recovery_case = case_response.json()
    duplicate = client.post(
        f"/api/v1/organizations/{organization_id}/recovery-cases",
        json={
            "opportunity_id": baseline["opportunity_id"],
            "baseline_id": baseline["id"],
            "idempotency_key": "case:one",
            "title": "Recover downtime value",
            "description": "Govern execution and finance verification.",
        },
    )
    assert duplicate.json()["id"] == recovery_case["id"]
    execution_response = client.post(
        f"/api/v1/organizations/{organization_id}/recovery-cases/{recovery_case['id']}/executions",
        json={"action_id": action["id"], "idempotency_key": "execution:one"},
    )
    assert execution_response.status_code == 201, execution_response.text
    execution_id = execution_response.json()["id"]
    for transition_name in ("start", "complete"):
        response = client.post(
            f"/api/v1/organizations/{organization_id}/recovery-executions/"
            f"{execution_id}/{transition_name}"
        )
        assert response.status_code == 200, response.text
    start = datetime.now(UTC) - timedelta(days=30)
    measurement_response = client.post(
        f"/api/v1/organizations/{organization_id}/recovery-executions/{execution_id}/measurements",
        json={
            "idempotency_key": "measurement:one",
            "category": "cost_reduction",
            "baseline_amount": "100000",
            "actual_amount": "72000",
            "currency_code": "USD",
            "measurement_start": start.isoformat(),
            "measurement_end": datetime.now(UTC).isoformat(),
            "methodology": "period_cost_comparison",
            "calculation_inputs": {"source_period": "prior_30_days"},
            "evidence": [
                {
                    "evidence_type": "financial_extract",
                    "source_type": "dataset",
                    "source_identifier": "dataset-version:verified-costs",
                }
            ],
        },
    )
    assert measurement_response.status_code == 201, measurement_response.text
    measurement = measurement_response.json()
    assert measurement["realized_value"] == "28000.000000000000"
    submitted = client.post(
        f"/api/v1/organizations/{organization_id}/recovery-measurements/{measurement['id']}/submit"
    )
    assert submitted.status_code == 200
    submitter = identity.user_id
    self_approval = client.post(
        f"/api/v1/organizations/{organization_id}/recovery-measurements/{measurement['id']}/verify",
        json={
            "idempotency_key": "verification:one",
            "verified_amount": "27500",
            "currency_code": "USD",
            "rationale": "Finance reconciled supporting evidence.",
        },
    )
    assert self_approval.status_code == 403
    identity.user_id = uuid4()
    verified = client.post(
        f"/api/v1/organizations/{organization_id}/recovery-measurements/{measurement['id']}/verify",
        json={
            "idempotency_key": "verification:one",
            "verified_amount": "27500",
            "currency_code": "USD",
            "rationale": "Finance reconciled supporting evidence.",
        },
    )
    assert verified.status_code == 201, verified.text
    assert verified.json()["entry_type"] == "verified_recovery"
    repeated = client.post(
        f"/api/v1/organizations/{organization_id}/recovery-measurements/{measurement['id']}/verify",
        json={
            "idempotency_key": "verification:one",
            "verified_amount": "27500",
            "currency_code": "USD",
            "rationale": "Finance reconciled supporting evidence.",
        },
    )
    assert repeated.status_code == 201
    assert repeated.json()["id"] == verified.json()["id"]
    original_id = verified.json()["id"]
    adjustment = client.post(
        f"/api/v1/organizations/{organization_id}/verified-value-ledger/{original_id}/adjustments",
        json={
            "idempotency_key": "adjustment:one",
            "amount": "500",
            "direction": "positive",
            "reason": "Late invoice reconciliation.",
        },
    )
    assert adjustment.status_code == 201
    reversal = client.post(
        f"/api/v1/organizations/{organization_id}/verified-value-ledger/{original_id}/reversals",
        json={
            "idempotency_key": "reversal:one",
            "amount": "2500",
            "reason": "Partial duplicate credit reversal.",
        },
    )
    assert reversal.status_code == 201
    too_large = client.post(
        f"/api/v1/organizations/{organization_id}/verified-value-ledger/{original_id}/reversals",
        json={
            "idempotency_key": "reversal:too-large",
            "amount": "26000",
            "reason": "Exceeds remaining amount.",
        },
    )
    assert too_large.status_code == 409
    summary = client.get(
        f"/api/v1/organizations/{organization_id}/recovery-cases/"
        f"{recovery_case['id']}/value-summary"
    )
    assert summary.status_code == 200
    values = summary.json()["currencies"][0]
    assert values["expected_value"] != values["realized_value"]
    assert values["realized_value"] == "28000.000000000000"
    assert values["verified_value"] == "27500.000000000000"
    assert values["net_verified_value"] == "25500.000000000000"
    command = client.get(
        f"/api/v1/organizations/{organization_id}/command/executive-summary",
        params={
            "period_start": start.isoformat(),
            "period_end": datetime.now(UTC).isoformat(),
        },
    )
    assert command.status_code == 200, command.text
    command_values = command.json()["currencies"][0]
    assert command_values["exposure"] == "100000.000000000000"
    assert command_values["addressable_exposure"] == "80000.000000000000"
    assert command_values["expected_recoverable_value"] == "60000.000000000000"
    assert command_values["realized_value"] == "28000.000000000000"
    assert command_values["verified_value"] == "27500.000000000000"
    assert command_values["adjustments"] == "500.000000000000"
    assert command_values["reversals"] == "-2500.000000000000"
    assert submitter != identity.user_id
    posted = db.scalar(
        select(VerifiedValueLedgerEntry).where(VerifiedValueLedgerEntry.id == UUID(original_id))
    )
    assert posted is not None
    posted.reason = "Attempted rewrite"
    try:
        db.commit()
    except ValueError as exc:
        assert "immutable" in str(exc)
        db.rollback()
    else:
        raise AssertionError("Posted ledger mutation was not rejected")


def test_recovery_tenant_and_currency_isolation(
    client: TestClient,
) -> None:
    first, _, baseline = approved_foundation(client, "recovery-first")
    second = organization(client, "recovery-second")
    created = client.post(
        f"/api/v1/organizations/{first}/recovery-cases",
        json={
            "opportunity_id": baseline["opportunity_id"],
            "baseline_id": baseline["id"],
            "idempotency_key": "tenant-case",
            "title": "Tenant-owned recovery",
            "description": "Must not cross organization boundary.",
        },
    )
    assert created.status_code == 201
    case_id = created.json()["id"]
    assert client.get(f"/api/v1/organizations/{second}/recovery-cases/{case_id}").status_code == 404
    assert client.get(f"/api/v1/organizations/{second}/verified-value-ledger").json()["total"] == 0
