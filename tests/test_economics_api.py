from uuid import uuid4

from conftest import IdentityState
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

JSON_OBJECT = TypeAdapter(dict[str, object])


def organization(client: TestClient, slug: str) -> str:
    response = client.post(
        "/api/v1/organizations",
        json={
            "name": slug,
            "slug": slug,
            "country_code": "US",
            "default_currency": "USD",
            "timezone": "UTC",
        },
    )
    assert response.status_code == 201
    return str(response.json()["id"])


def opportunity(client: TestClient, organization_id: str, key: str, currency: str = "USD") -> dict:
    response = client.post(
        f"/api/v1/organizations/{organization_id}/recovery-opportunities",
        json={
            "idempotency_key": key,
            "economic_source_key": f"source:{key}",
            "title": "Recover avoidable downtime exposure",
            "description": "Quantify the expected economics before operational action.",
            "currency_code": currency,
            "business_domain": "maintenance",
            "site_reference": "SITE-01",
        },
    )
    assert response.status_code == 201, response.text
    return JSON_OBJECT.validate_python(response.json())


def scenario(client: TestClient, organization_id: str, opportunity_id: str) -> dict:
    response = client.post(
        f"/api/v1/organizations/{organization_id}/recovery-opportunities/"
        f"{opportunity_id}/scenarios",
        json={
            "scenario_code": "base",
            "name": "Base case",
            "currency_code": "USD",
            "lower_exposure": "80000",
            "gross_exposure": "100000",
            "upper_exposure": "125000",
            "addressability_rate": "0.8",
            "recoverability_rate": "0.75",
            "success_probability": "0.6",
            "recovery_cost": "6000",
            "benefit_period_days": 180,
            "scenario_probability": "0.6",
            "assumptions_summary": ["Based on validated downtime and cost evidence."],
        },
    )
    assert response.status_code == 201, response.text
    return JSON_OBJECT.validate_python(response.json())


def calculate_and_prioritize(
    client: TestClient, organization_id: str, opportunity_id: str, scenario_id: str
) -> tuple[dict, dict]:
    calculated = client.post(
        f"/api/v1/organizations/{organization_id}/recovery-opportunities/"
        f"{opportunity_id}/calculate",
        json={"scenario_id": scenario_id, "idempotency_key": f"calc:{opportunity_id}"},
    )
    assert calculated.status_code == 200, calculated.text
    prioritized = client.post(
        f"/api/v1/organizations/{organization_id}/recovery-opportunities/"
        f"{opportunity_id}/prioritize",
        json={
            "calculation_id": calculated.json()["id"],
            "idempotency_key": f"priority:{opportunity_id}",
            "profile_code": "default_enterprise",
            "urgency_score": "0.9",
            "confidence_score": "0.8",
            "feasibility_score": "0.7",
            "strategic_alignment_score": "0.6",
            "risk_score": "0.2",
            "calculation_reason": "Rank approved economic evidence.",
        },
    )
    assert prioritized.status_code == 200, prioritized.text
    return calculated.json(), prioritized.json()


def decide(
    client: TestClient,
    organization_id: str,
    opportunity_id: str,
    decision: str,
    *,
    scenario_id: str | None = None,
    prioritization_id: str | None = None,
) -> dict:
    response = client.post(
        f"/api/v1/organizations/{organization_id}/recovery-opportunities/"
        f"{opportunity_id}/{'approve' if decision == 'approved_for_action' else 'submit'}",
        json={
            "decision": decision,
            "decision_reason": f"Governed decision: {decision}",
            "idempotency_key": f"{opportunity_id}:{decision}",
            "scenario_id": scenario_id,
            "prioritization_id": prioritization_id,
        },
    )
    assert response.status_code == 200, response.text
    return JSON_OBJECT.validate_python(response.json())


def test_recovery_economics_end_to_end_and_baseline_immutability(
    client: TestClient,
) -> None:
    organization_id = organization(client, "economics-loop")
    created = opportunity(client, organization_id, "loop-1")
    opportunity_id = created["id"]
    assert opportunity(client, organization_id, "loop-1")["id"] == opportunity_id
    case = scenario(client, organization_id, opportunity_id)
    assumption = client.post(
        f"/api/v1/organizations/{organization_id}/recovery-opportunities/"
        f"{opportunity_id}/assumptions",
        json={
            "scenario_id": case["id"],
            "assumption_code": "DOWNTIME_COST",
            "value": "10000",
            "unit": "currency_per_day",
            "currency_code": "USD",
            "source": "finding_evidence",
            "evidence_reference": "evidence:downtime-ledger",
            "confidence_score": "0.8",
            "model_version": "1.0",
        },
    )
    assert assumption.status_code == 201
    revised = client.patch(
        f"/api/v1/organizations/{organization_id}/recovery-opportunities/"
        f"{opportunity_id}/assumptions/{assumption.json()['id']}",
        json={
            "scenario_id": case["id"],
            "assumption_code": "DOWNTIME_COST",
            "value": "10500",
            "unit": "currency_per_day",
            "currency_code": "USD",
            "source": "finding_evidence",
            "evidence_reference": "evidence:downtime-ledger-revised",
            "confidence_score": "0.85",
            "model_version": "1.0",
        },
    )
    assert revised.status_code == 200
    assert revised.json()["version"] == 2
    missing_revision = client.patch(
        f"/api/v1/organizations/{organization_id}/recovery-opportunities/"
        f"{opportunity_id}/assumptions/{uuid4()}",
        json={
            "assumption_code": "DOWNTIME_COST",
            "value": "1",
            "unit": "currency_per_day",
            "currency_code": "USD",
            "source": "manual",
            "confidence_score": "1",
        },
    )
    assert missing_revision.status_code == 404
    calculated, prioritized = calculate_and_prioritize(
        client, organization_id, opportunity_id, case["id"]
    )
    assert calculated["expected_net_benefit"] == "30000.000000000000"
    assert calculated["expected_roi"] == "5.000000000000"
    assert prioritized["factor_contributions"]

    decide(client, organization_id, opportunity_id, "under_review")
    decide(
        client,
        organization_id,
        opportunity_id,
        "economically_qualified",
        scenario_id=case["id"],
        prioritization_id=prioritized["id"],
    )
    approved = decide(
        client,
        organization_id,
        opportunity_id,
        "approved_for_action",
        scenario_id=case["id"],
        prioritization_id=prioritized["id"],
    )
    assert approved["baseline"]["version"] == 1
    assert "realized" not in str(approved["baseline"]).lower()
    immutable = client.patch(
        f"/api/v1/organizations/{organization_id}/recovery-opportunities/{opportunity_id}",
        json={"title": "Mutated approved title"},
    )
    assert immutable.status_code == 422

    economics = client.get(
        f"/api/v1/organizations/{organization_id}/recovery-opportunities/{opportunity_id}/economics"
    )
    explanation = client.get(
        f"/api/v1/organizations/{organization_id}/recovery-opportunities/"
        f"{opportunity_id}/priority-explanation"
    )
    audit = client.get(
        f"/api/v1/organizations/{organization_id}/recovery-opportunities/"
        f"{opportunity_id}/audit-trail"
    )
    assert economics.status_code == explanation.status_code == audit.status_code == 200
    event_types = [item["event_type"] for item in audit.json()]
    assert {
        "opportunity_created",
        "scenario_created",
        "assumption_version_created",
        "calculation_run",
        "prioritization_run",
        "decision_recorded",
    } <= set(event_types)


def test_tenant_relationships_overlap_and_currency_separated_portfolio(
    client: TestClient,
) -> None:
    first = organization(client, "economics-first")
    second = organization(client, "economics-second")
    first_opportunity = opportunity(client, first, "first")
    second_opportunity = opportunity(client, second, "second", "EUR")
    assert (
        client.get(
            f"/api/v1/organizations/{second}/recovery-opportunities/{first_opportunity['id']}"
        ).status_code
        == 404
    )
    missing_finding = client.post(
        f"/api/v1/organizations/{first}/recovery-opportunities/{first_opportunity['id']}/findings",
        json={"finding_id": str(uuid4()), "allocation_percentage": "1"},
    )
    assert missing_finding.status_code == 404

    case = scenario(client, first, first_opportunity["id"])
    calculate_and_prioritize(client, first, first_opportunity["id"], case["id"])
    group = client.post(
        f"/api/v1/organizations/{first}/recovery-overlap-groups",
        json={
            "overlap_key": "downtime:SITE-01:2026",
            "overlap_type": "partial",
            "decision_reason": "Allocate shared downtime exposure.",
        },
    )
    assert group.status_code == 201
    member = client.post(
        f"/api/v1/organizations/{first}/recovery-overlap-groups/{group.json()['id']}/members",
        json={
            "opportunity_id": first_opportunity["id"],
            "allocation_percentage": "0.5",
            "inclusion_status": "included",
        },
    )
    assert member.status_code == 201
    summary = client.get(f"/api/v1/organizations/{first}/recovery-portfolio/summary")
    ranking = client.get(f"/api/v1/organizations/{first}/recovery-portfolio/ranking")
    assert summary.status_code == ranking.status_code == 200
    assert summary.json()["currencies"][0]["currency_code"] == "USD"
    assert summary.json()["currencies"][0]["probability_adjusted_value"] == "18000.000000000000"
    assert all(item["opportunity"]["organization_id"] == first for item in ranking.json())
    assert second_opportunity["organization_id"] == second


def test_viewer_can_read_but_cannot_modify_or_approve_economics(
    client: TestClient,
    identity: IdentityState,
) -> None:
    organization_id = organization(client, "economics-permissions")
    created = opportunity(client, organization_id, "permissions")
    viewer_id = uuid4()
    membership = client.post(
        f"/api/v1/organizations/{organization_id}/members",
        json={"user_id": str(viewer_id), "role": "viewer", "status": "active"},
    )
    assert membership.status_code == 201
    identity.user_id = viewer_id
    identity.is_platform_admin = False

    assert (
        client.get(
            f"/api/v1/organizations/{organization_id}/recovery-opportunities/{created['id']}"
        ).status_code
        == 200
    )
    assumption = client.post(
        f"/api/v1/organizations/{organization_id}/recovery-opportunities/"
        f"{created['id']}/assumptions",
        json={
            "assumption_code": "UNAUTHORIZED",
            "value": "1",
            "unit": "count",
            "source": "manual",
            "confidence_score": "1",
        },
    )
    assert assumption.status_code == 403
    approval = client.post(
        f"/api/v1/organizations/{organization_id}/recovery-opportunities/{created['id']}/approve",
        json={
            "decision": "approved_for_action",
            "decision_reason": "Unauthorized",
            "idempotency_key": "unauthorized-approval",
        },
    )
    assert approval.status_code == 403
