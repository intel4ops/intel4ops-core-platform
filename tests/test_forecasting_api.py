from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_forecasting_service import foundation, payload

from app.schemas.forecasting import ForecastScenarioCreate


def test_forecasting_api_execution_methods_evidence_scenario_and_actual(
    client: TestClient, db: Session
) -> None:
    organization_id, trust_id, readiness_id, _ = foundation(db, "forecast-api")
    request = payload(trust_id, readiness_id, "9" * 64)
    response = client.post(
        f"/api/v1/organizations/{organization_id}/forecasts/executions",
        json=request.model_dump(mode="json"),
    )
    assert response.status_code == 201
    execution = response.json()
    execution_id = execution["id"]
    assert execution["status"] == "succeeded"

    listed = client.get(f"/api/v1/organizations/{organization_id}/forecasts/executions")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    methods = client.get(f"/api/v1/organizations/{organization_id}/forecasts/methods")
    assert methods.status_code == 200
    assert len(methods.json()) == 19
    assert (
        client.get(f"/api/v1/organizations/{organization_id}/forecasts/methods/NAIVE").status_code
        == 200
    )

    candidates = client.get(
        f"/api/v1/organizations/{organization_id}/forecasts/executions/{execution_id}/candidates"
    )
    assert candidates.status_code == 200
    assert any(item["selected"] for item in candidates.json())
    points = client.get(
        f"/api/v1/organizations/{organization_id}/forecasts/executions/{execution_id}/points"
    )
    assert points.status_code == 200
    baseline = points.json()
    assert len(baseline) == 3
    evidence = client.get(
        f"/api/v1/organizations/{organization_id}/forecasts/executions/{execution_id}/evidence"
    )
    assert evidence.status_code == 200
    assert evidence.json()["raw_records_included"] is False

    scenario = ForecastScenarioCreate(
        scenario_code="STRESS",
        name="Stress case",
        description="Demand is reduced by twenty percent.",
        adjustment_type="PERCENTAGE",
        adjustment_amount=-20,
        effective_from=datetime.now(UTC),
        effective_to=datetime.now(UTC).replace(year=datetime.now(UTC).year + 1),
    )
    scenario_response = client.post(
        f"/api/v1/organizations/{organization_id}/forecasts/executions/{execution_id}/scenarios",
        json=scenario.model_dump(mode="json"),
    )
    assert scenario_response.status_code == 201
    actual = client.post(
        f"/api/v1/organizations/{organization_id}/forecasts/points/{baseline[0]['id']}/actual",
        json={
            "actual_reference": "dataset:actual:period-1",
            "actual_value": baseline[0]["point_forecast"],
            "dataset_id": str(request.dataset_id),
            "dataset_version_id": str(request.dataset_version_id),
        },
    )
    assert actual.status_code == 200
    legacy_payload = request.model_dump(mode="json")
    legacy_payload["dataset_reference"] = "caller-controlled-reference"
    rejected = client.post(
        f"/api/v1/organizations/{organization_id}/forecasts/executions",
        json=legacy_payload,
    )
    assert rejected.status_code == 422
    accuracy = client.get(
        f"/api/v1/organizations/{organization_id}/forecasts/executions/{execution_id}/accuracy"
    )
    assert accuracy.status_code == 200
    assert len(accuracy.json()) == 1
    assert (
        client.get(
            f"/api/v1/organizations/{uuid4()}/forecasts/executions/{execution_id}"
        ).status_code
        == 404
    )


def test_forecast_evaluate_returns_structured_unsupported_status(
    client: TestClient, db: Session
) -> None:
    organization_id, _, _, _ = foundation(db, "forecast-evaluate")
    response = client.post(
        f"/api/v1/organizations/{organization_id}/forecasts/evaluate",
        json={"method_code": "ARIMA", "values": [1, 2, 3], "horizon": 2},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "unsupported"
