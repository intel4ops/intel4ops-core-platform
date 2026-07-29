from conftest import IdentityState
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_reliability_service import reliability_foundation, reliability_payload


def test_reliability_api_exposes_truthful_metadata_and_human_review_evidence(
    client: TestClient, db: Session
) -> None:
    organization_id, trust_id, readiness_id, _ = reliability_foundation(db, "reliability-api")
    methods = client.get(f"/api/v1/organizations/{organization_id}/reliability/methods")
    assert methods.status_code == 200
    weibull = next(
        item for item in methods.json() if item["method_code"] == "WEIBULL_TWO_PARAMETER"
    )
    assert weibull["supports_censoring"] is False
    assert any("uncensored" in item.lower() for item in weibull["known_limitations"])

    request = reliability_payload(trust_id, readiness_id, dataset_fingerprint="9" * 64)
    response = client.post(
        f"/api/v1/organizations/{organization_id}/reliability/executions",
        json=request.model_dump(mode="json"),
    )
    assert response.status_code == 201
    execution_id = response.json()["id"]
    evidence = client.get(
        f"/api/v1/organizations/{organization_id}/reliability/executions/{execution_id}/evidence"
    )
    assert evidence.status_code == 200
    assert evidence.json()["explanation"]["human_review_required"] is True
    assert evidence.json()["explanation"]["recommended_action_category"] == "HUMAN_REVIEW"


def test_reliability_evaluate_rejects_censored_weibull_and_fractional_counts(
    client: TestClient, db: Session
) -> None:
    organization_id, _, _, _ = reliability_foundation(db, "reliability-api-validation")
    censored = client.post(
        f"/api/v1/organizations/{organization_id}/reliability/evaluate",
        json={
            "method_code": "WEIBULL_TWO_PARAMETER",
            "observations": [
                {"duration": 10, "event_observed": True},
                {"duration": 20, "event_observed": True},
                {"duration": 40, "event_observed": True},
                {"duration": 50, "event_observed": False},
            ],
        },
    )
    assert censored.status_code == 422
    assert censored.json()["detail"]["code"] == "METHOD_REJECTED"
    assert "does not support censored" in censored.json()["detail"]["message"]

    fractional = client.post(
        f"/api/v1/organizations/{organization_id}/reliability/evaluate",
        json={
            "method_code": "BASIC_RELIABILITY_METRICS",
            "observations": [{"exposure": 100, "failure_count": 1.5}],
        },
    )
    assert fractional.status_code == 422


def test_reliability_api_requires_authentication(
    client: TestClient, db: Session, identity: IdentityState
) -> None:
    organization_id, _, _, _ = reliability_foundation(db, "reliability-api-auth")
    identity.user_id = None

    response = client.get(f"/api/v1/organizations/{organization_id}/reliability/methods")

    assert response.status_code == 401


def test_reliability_api_requires_organization_authorization(
    client: TestClient, db: Session, identity: IdentityState
) -> None:
    organization_id, _, _, _ = reliability_foundation(db, "reliability-api-authorization")
    identity.is_platform_admin = False

    response = client.get(f"/api/v1/organizations/{organization_id}/reliability/methods")

    assert response.status_code == 403
