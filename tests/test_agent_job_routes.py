"""AGENTIC-CONTROL-001 Phase E/P: API-level tests for
app/api/agent_job_routes.py. Two distinct auth surfaces are exercised
here on purpose: the human-session endpoints (create, get, owner-decision,
worker-credentials) via the platform-admin `client` fixture, and the
worker-credential endpoints (claim/heartbeat/result/failure) via a real
`Authorization: Bearer <token>` header -- never the Supabase session."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


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


def _evidence_package_payload(risk_class: str = "R0") -> dict:
    return {
        "work_item_id": "route-test-1",
        "evidence_plane": "production",
        "risk_class": risk_class,
        "observation": {"observed_behavior": "observed via HTTP"},
        "impact": {},
        "evidence": {},
        "control": {},
        "safety": {},
        "code_context": {},
        "question": "classify this",
    }


def test_create_and_get_agent_job_via_http(client: TestClient) -> None:
    org_id = create_organization(client, "route-create")
    response = client.post(
        f"/api/v1/organizations/{org_id}/agent-jobs",
        json={
            "job_type": "PRODUCTION_TRIAGE",
            "risk_class": "R0",
            "requested_capability": "gap_classification_v1",
            "evidence_package": _evidence_package_payload(),
        },
    )
    assert response.status_code == 201, response.text
    job = response.json()
    assert job["status"] == "queued"
    assert job["risk_class"] == "R0"

    fetched = client.get(f"/api/v1/organizations/{org_id}/agent-jobs/{job['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == job["id"]


def test_r2_job_via_http_is_owner_review_required(client: TestClient) -> None:
    org_id = create_organization(client, "route-r2")
    response = client.post(
        f"/api/v1/organizations/{org_id}/agent-jobs",
        json={
            "job_type": "PLATFORM_CHANGE",
            "risk_class": "R2",
            "requested_capability": "platform_review_v1",
            "evidence_package": _evidence_package_payload(risk_class="R2"),
        },
    )
    assert response.status_code == 201, response.text
    job = response.json()
    assert job["status"] == "owner_review_required"
    assert job["owner_approval_required"] is True
    assert job["owner_approval_status"] == "pending"


def test_owner_decision_approves_a_gated_job(client: TestClient) -> None:
    org_id = create_organization(client, "route-owner-decision")
    created = client.post(
        f"/api/v1/organizations/{org_id}/agent-jobs",
        json={
            "job_type": "PLATFORM_CHANGE",
            "risk_class": "R2",
            "requested_capability": "platform_review_v1",
            "evidence_package": _evidence_package_payload(risk_class="R2"),
        },
    ).json()

    decided = client.post(
        f"/api/v1/organizations/{org_id}/agent-jobs/{created['id']}/owner-decision",
        json={"approve": True, "note": "reviewed offline, safe to proceed"},
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["owner_approval_status"] == "approved"

    # A second decision on the same job is rejected -- a decision is recorded once.
    redecide = client.post(
        f"/api/v1/organizations/{org_id}/agent-jobs/{created['id']}/owner-decision",
        json={"approve": True, "note": "again"},
    )
    assert redecide.status_code == 409


def test_worker_credential_issuance_and_full_claim_lifecycle_over_http(client: TestClient) -> None:
    org_id = create_organization(client, "route-worker-lifecycle")

    created = client.post(
        f"/api/v1/organizations/{org_id}/agent-jobs",
        json={
            "job_type": "PRODUCTION_TRIAGE",
            "risk_class": "R0",
            "requested_capability": "gap_classification_v1",
            "evidence_package": _evidence_package_payload(),
        },
    ).json()

    credential_response = client.post(
        f"/api/v1/organizations/{org_id}/agent-jobs/worker-credentials",
        params={"worker_id": f"test-worker-{uuid4().hex[:8]}"},
    )
    assert credential_response.status_code == 201, credential_response.text
    token = credential_response.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    claim_response = client.post(
        f"/api/v1/organizations/{org_id}/agent-jobs/claim", headers=headers
    )
    assert claim_response.status_code == 200
    claimed = claim_response.json()
    assert claimed["job"]["id"] == created["id"]
    assert claimed["model_profile"] == "QWEN_R0"
    assert claimed["model_parameters"]["max_output_tokens"] == 180
    lease_id = claimed["lease_id"]

    heartbeat_response = client.post(
        f"/api/v1/organizations/{org_id}/agent-jobs/{created['id']}/heartbeat",
        json={"lease_id": lease_id},
        headers=headers,
    )
    assert heartbeat_response.status_code == 204

    result_response = client.post(
        f"/api/v1/organizations/{org_id}/agent-jobs/{created['id']}/result",
        json={
            "lease_id": lease_id,
            "structured_result": {
                "primary_gap_class": "DATA_CONTRACT_GAP",
                "secondary_gap_classes": [],
                "confidence": 95,
                "summary": "classified over http",
                "evidence_refs": [],
                "fp_risk": "low",
                "architecture_impact": False,
                "policy_dependency": False,
                "data_contract_dependency": True,
                "recommended_action": "none",
                "escalate": False,
                "escalation_reason": None,
            },
            "execution_time_ms": 800,
            "input_tokens": 300,
            "output_tokens": 100,
            "reasoning_tokens": 0,
            "model_identifier": "qwen/qwen3.5-9b",
        },
        headers=headers,
    )
    assert result_response.status_code == 200, result_response.text
    assert result_response.json()["status"] == "succeeded"

    # A second claim now finds nothing -- the job is already terminal.
    second_claim = client.post(f"/api/v1/organizations/{org_id}/agent-jobs/claim", headers=headers)
    assert second_claim.status_code == 200
    assert second_claim.json() is None


def test_claim_without_worker_credential_is_unauthorized(client: TestClient) -> None:
    org_id = create_organization(client, "route-no-auth")
    response = client.post(f"/api/v1/organizations/{org_id}/agent-jobs/claim")
    assert response.status_code == 401


def test_r2_job_is_never_claimable_by_a_worker_credential_over_http(client: TestClient) -> None:
    org_id = create_organization(client, "route-r2-unclaimable")
    client.post(
        f"/api/v1/organizations/{org_id}/agent-jobs",
        json={
            "job_type": "PLATFORM_CHANGE",
            "risk_class": "R2",
            "requested_capability": "platform_review_v1",
            "evidence_package": _evidence_package_payload(risk_class="R2"),
        },
    )
    credential_response = client.post(
        f"/api/v1/organizations/{org_id}/agent-jobs/worker-credentials",
        params={"worker_id": f"test-worker-{uuid4().hex[:8]}"},
    )
    headers = {"Authorization": f"Bearer {credential_response.json()['token']}"}
    claim_response = client.post(
        f"/api/v1/organizations/{org_id}/agent-jobs/claim", headers=headers
    )
    assert claim_response.status_code == 200
    assert claim_response.json() is None


def test_claim_endpoint_opportunistically_recovers_a_stale_job_before_dispatching(
    client: TestClient, db: Session
) -> None:
    """Phase O: a run/job that silently stops sending heartbeats must
    never sit at RUNNING forever with no external signal -- unlike
    RUN-RELIABILITY-001's production-run path, /claim proactively sweeps
    stale AgentJobs (via AgentJobService.recover_stale) before every
    dispatch, so a dead worker's job gets requeued and reclaimed on the
    very next poll instead of needing a manual /status query."""
    from app.models.agent_jobs import AgentJob, AgentJobStatus

    org_id = create_organization(client, "route-stale-recovery")
    created = client.post(
        f"/api/v1/organizations/{org_id}/agent-jobs",
        json={
            "job_type": "PRODUCTION_TRIAGE",
            "risk_class": "R0",
            "requested_capability": "gap_classification_v1",
            "evidence_package": _evidence_package_payload(),
        },
    ).json()

    credential_response = client.post(
        f"/api/v1/organizations/{org_id}/agent-jobs/worker-credentials",
        params={"worker_id": f"stale-worker-{uuid4().hex[:8]}"},
    )
    headers = {"Authorization": f"Bearer {credential_response.json()['token']}"}

    first_claim = client.post(f"/api/v1/organizations/{org_id}/agent-jobs/claim", headers=headers)
    assert first_claim.status_code == 200
    assert first_claim.json() is not None

    # Simulate the worker vanishing: back-date the heartbeat far beyond
    # the stale threshold without ever submitting a result or failure.
    job = db.get(AgentJob, UUID(created["id"]))
    assert job is not None
    job.heartbeat_at = datetime.now(UTC) - timedelta(hours=1)
    db.commit()

    second_claim = client.post(f"/api/v1/organizations/{org_id}/agent-jobs/claim", headers=headers)
    assert second_claim.status_code == 200
    reclaimed = second_claim.json()
    assert reclaimed is not None
    assert reclaimed["job"]["id"] == created["id"]
    assert reclaimed["job"]["status"] == AgentJobStatus.RUNNING.value
    assert reclaimed["job"]["retry_count"] == 1
