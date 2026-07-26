from uuid import uuid4

from fastapi.testclient import TestClient


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


def action_payload(source: str = "manual") -> dict[str, object]:
    return {
        "source_type": source,
        "source_reference": "manual:pump-p-204:inspection",
        "recommendation_type": "inspection",
        "recommendation_rule_version": "1.0",
        "title": "Inspect pump P-204",
        "description": "Inspect the drive-end bearing before the risk horizon.",
        "rationale": "Elevated reliability risk requires verification before repair.",
        "asset_reference": "P-204",
        "component_reference": "drive-end-bearing",
        "failure_mode": "bearing_degradation",
        "failure_probability": "0.82",
        "prediction_horizon_days": 18,
        "severity": 5,
        "confidence_score": "0.85",
        "expected_avoided_cost": "80000.00",
        "expected_intervention_cost": "2500.00",
        "currency_code": "USD",
        "verification_required": True,
        "limitations": ["Inventory status requires confirmation."],
    }


def transition(client: TestClient, organization_id: str, action_id: str, status: str) -> object:
    response = client.post(
        f"/api/v1/organizations/{organization_id}/actions/{action_id}/transition",
        json={
            "new_status": status,
            "reason_code": f"TEST_{status.upper()}",
            "idempotency_key": f"{action_id}:{status}",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_action_idempotency_tenancy_and_closed_loop(client: TestClient) -> None:
    first = organization(client, "action-loop-first")
    second = organization(client, "action-loop-second")
    created = client.post(f"/api/v1/organizations/{first}/actions", json=action_payload())
    assert created.status_code == 201
    action = created.json()
    action_id = action["id"]
    duplicate = client.post(f"/api/v1/organizations/{first}/actions", json=action_payload())
    assert duplicate.status_code == 201
    assert duplicate.json()["id"] == action_id
    assert client.get(f"/api/v1/organizations/{second}/actions/{action_id}").status_code == 404
    assert client.get(f"/api/v1/organizations/{first}/actions").json()["total"] == 1

    plan = client.post(
        f"/api/v1/organizations/{first}/actions/{action_id}/plan",
        json={
            "sequence_number": 1,
            "title": "Inspect bearing",
            "description": "Capture vibration and temperature evidence.",
            "required_skill": "reliability_engineer",
            "estimated_labor_hours": "4.0",
        },
    )
    assert plan.status_code == 201
    part = client.post(
        f"/api/v1/organizations/{first}/actions/{action_id}/resources",
        json={
            "resource_type": "part",
            "resource_identifier": "BRG-204",
            "description": "Drive-end bearing",
            "required_quantity": "1",
            "available_quantity": "1",
            "mandatory": True,
        },
    )
    assert part.status_code == 201
    expected = client.post(
        f"/api/v1/organizations/{first}/actions/{action_id}/outcomes",
        json={
            "outcome_type": "expected",
            "avoided_cost": "80000.00",
            "intervention_cost": "2500.00",
            "currency_code": "USD",
            "calculation_method": "bounded_expected_value",
        },
    )
    assert expected.status_code == 201
    premature = client.post(
        f"/api/v1/organizations/{first}/actions/{action_id}/outcomes",
        json={
            "outcome_type": "realized",
            "avoided_cost": "75000.00",
            "currency_code": "USD",
            "calculation_method": "verified_reconciliation",
        },
    )
    assert premature.status_code == 422

    for status in (
        "pending_approval",
        "approved",
        "assigned",
        "scheduled",
        "in_progress",
        "completed",
    ):
        transition(client, first, action_id, status)
    detail = client.get(f"/api/v1/organizations/{first}/actions/{action_id}").json()
    assert detail["status"] == "completed"
    assert detail["verified_at"] is None
    transition(client, first, action_id, "verification_pending")
    assert (
        client.post(
            f"/api/v1/organizations/{first}/actions/{action_id}/transition",
            json={
                "new_status": "verified",
                "reason_code": "NO_EVIDENCE",
                "idempotency_key": str(uuid4()),
            },
        ).status_code
        == 422
    )
    evidence = client.post(
        f"/api/v1/organizations/{first}/actions/{action_id}/evidence",
        json={
            "lifecycle_stage": "verification",
            "evidence_type": "inspection_result",
            "source_type": "manual",
            "source_identifier": "inspection:P-204",
            "measurement_value": "2.1",
            "measurement_unit": "mm/s",
            "notes": "Post-intervention vibration is acceptable.",
        },
    )
    assert evidence.status_code == 201
    transition(client, first, action_id, "verified")
    realized = client.post(
        f"/api/v1/organizations/{first}/actions/{action_id}/outcomes",
        json={
            "outcome_type": "realized",
            "avoided_cost": "75000.00",
            "intervention_cost": "2600.00",
            "currency_code": "USD",
            "calculation_method": "verified_reconciliation",
            "verification_method": "inspection_result",
        },
    )
    assert realized.status_code == 201
    history = client.get(f"/api/v1/organizations/{first}/actions/{action_id}/history")
    assert history.status_code == 200
    assert [item["event_type"] for item in history.json()][0] == "created"


def test_invalid_transition_and_source_validation(client: TestClient) -> None:
    organization_id = organization(client, "action-invalid")
    created = client.post(
        f"/api/v1/organizations/{organization_id}/actions", json=action_payload()
    ).json()
    invalid = client.post(
        f"/api/v1/organizations/{organization_id}/actions/{created['id']}/transition",
        json={
            "new_status": "verified",
            "reason_code": "INVALID",
            "idempotency_key": "invalid-transition",
        },
    )
    assert invalid.status_code == 409
    reliability = action_payload("reliability")
    reliability["reliability_execution_id"] = str(uuid4())
    missing = client.post(
        f"/api/v1/organizations/{organization_id}/actions/from-reliability",
        json=reliability,
    )
    assert missing.status_code == 404
