from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.gateway import ApplicationClient


def _organization(client: TestClient, slug: str) -> str:
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


def test_gateway_context_j2c_idempotency_and_empty_command(client: TestClient, db: Session) -> None:
    db.add(
        ApplicationClient(
            client_code="intel4ops-web",
            name="Intel4Ops Web",
            client_type="first_party",
        )
    )
    db.commit()
    org = _organization(client, "wp218-api")
    context = client.get(
        f"/api/v1/organizations/{org}/gateway/context",
        headers={"X-Request-ID": "request-wp218", "X-Correlation-ID": "correlation-wp218"},
    )
    assert context.status_code == 200, context.text
    assert context.json()["request_id"] == "request-wp218"
    assert context.headers["x-correlation-id"] == "correlation-wp218"

    payload = {
        "idempotency_key": "demo:1",
        "currency_code": "USD",
        "as_of": "2026-03-01",
        "records": [
            {
                "type": "job",
                "id": "J1",
                "data": {
                    "status": "completed",
                    "completed_at": "2026-01-01",
                    "billing_window_days": 5,
                    "contractual_charges": "100",
                    "expected_revenue": "100",
                    "governed_cost": "50",
                },
            }
        ],
    }
    first = client.post(f"/api/v1/organizations/{org}/job-to-cash/runs", json=payload)
    second = client.post(f"/api/v1/organizations/{org}/job-to-cash/runs", json=payload)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["findings"][0]["code"] == "COMPLETED_UNBILLED"

    now = datetime.now(UTC)
    summary = client.get(
        f"/api/v1/organizations/{org}/command/executive-summary",
        params={
            "period_start": now.replace(day=1).isoformat(),
            "period_end": now.isoformat(),
        },
    )
    assert summary.status_code == 200, summary.text
    assert summary.json()["currencies"] == []


def test_j2c_runs_are_tenant_scoped(client: TestClient) -> None:
    first = _organization(client, "wp218-first")
    second = _organization(client, "wp218-second")
    payload = {
        "idempotency_key": "same-key",
        "currency_code": "USD",
        "as_of": "2026-03-01",
        "records": [
            {
                "type": "job",
                "id": "J1",
                "data": {
                    "status": "completed",
                    "completed_at": "2026-01-01",
                    "contractual_charges": "10",
                },
            }
        ],
    }
    a = client.post(f"/api/v1/organizations/{first}/job-to-cash/runs", json=payload)
    b = client.post(f"/api/v1/organizations/{second}/job-to-cash/runs", json=payload)
    assert a.status_code == b.status_code == 201
    assert a.json()["id"] != b.json()["id"]


def test_gateway_error_envelope_does_not_expose_internals(client: TestClient) -> None:
    org = _organization(client, "wp218-errors")
    response = client.get(
        f"/api/v1/organizations/{org}/gateway/context",
        headers={
            "X-Request-ID": "error-request",
            "X-Intel4Ops-Client": "unknown-client",
        },
    )
    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "CLIENT_NOT_REGISTERED",
            "message": "Application client is not registered",
            "request_id": "error-request",
            "details": {},
            "field_errors": [],
        }
    }
