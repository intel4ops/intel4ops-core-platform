from uuid import UUID, uuid4

import pytest
from conftest import IdentityState
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_decision_intelligence_foundation import make_org
from test_p3_08_recovery_workspace import _finding
from test_p3_09_recovery_portfolio import _verified_chain

from app.models.learning import LearningSourceCase, OperationalLearning


def _memory(org: UUID, finding: UUID) -> str:
    return f"/api/v1/organizations/{org}/findings/{finding}/operational-memory"


def _learning(org: UUID, suffix: str = "") -> str:
    return f"/api/v1/organizations/{org}/learning{suffix}"


def test_operational_memory_auth_partial_and_foreign_scope(
    client: TestClient, identity: IdentityState, db: Session
) -> None:
    identity.user_id = None
    assert client.get(_memory(uuid4(), uuid4())).status_code == 401
    organization_id, _ = make_org(db, "p310-partial")
    finding = _finding(db, organization_id, "PARTIAL")
    identity.is_platform_admin = True
    identity.user_id = uuid4()
    response = client.get(_memory(organization_id, finding.id))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["finding"]["id"] == str(finding.id)
    assert body["recovery_workspace"]["action"] is None
    assert body["eligibility"]["eligible"] is False
    assert "recommendation_missing" in body["eligibility"]["reasons"]
    foreign_id, _ = make_org(db, "p310-foreign")
    assert client.get(_memory(foreign_id, finding.id)).status_code == 404


def test_full_memory_keeps_expected_realized_verified_and_history_distinct(
    client: TestClient, identity: IdentityState, db: Session
) -> None:
    organization_id, finding, _, _ = _verified_chain(client, identity, db, "p310-memory")
    body = client.get(_memory(organization_id, finding.id)).json()
    workspace = body["recovery_workspace"]
    assert (
        workspace["recovery_case"]["expected_value"]
        != workspace["measurements"][-1]["realized_value"]
    )
    assert (
        workspace["measurements"][-1]["realized_value"]
        != workspace["verified_ledger"][-1]["amount"]
    )
    assert workspace["action_outcomes"]
    assert workspace["measurement_evidence"]
    assert workspace["recovery_history"]
    assert body["eligibility"] == {
        "eligible": True,
        "reasons": [],
        "has_outcome": True,
        "has_realized_value": True,
        "has_verified_value": True,
        "provenance_type": "manual",
    }


def test_learning_candidate_governance_audit_and_retrieval(
    client: TestClient, identity: IdentityState, db: Session
) -> None:
    organization_id, finding, _, _ = _verified_chain(client, identity, db, "p310-learning")
    create = client.post(
        _learning(organization_id),
        json={
            "learning_type": "corrective_action",
            "title": "Governed corrective action",
            "statement": "This case supports reuse within the stated equipment and process scope.",
            "scope": "This organization and the same governed operating context only.",
            "source_finding_ids": [str(finding.id)],
            "value_basis": "verified_ledger",
        },
    )
    assert create.status_code == 201, create.text
    candidate = create.json()
    assert candidate["status"] == "candidate"
    assert candidate["provenance_type"] == "manual"
    assert candidate["value_basis"] == "verified_ledger"
    assert candidate["source_cases"][0]["finding_id"] == str(finding.id)
    learning_id = candidate["id"]
    reviewed = client.post(
        _learning(organization_id, f"/{learning_id}/review"),
        json={"transition": "review", "rationale": "Evidence basis reviewed."},
    )
    assert reviewed.status_code == 200, reviewed.text
    approved = client.post(
        _learning(organization_id, f"/{learning_id}/approve"),
        json={"transition": "approve", "rationale": "Approved for bounded reuse."},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved_for_reuse"
    assert [event["new_status"] for event in approved.json()["audit_history"]] == [
        "candidate",
        "reviewed",
        "approved_for_reuse",
    ]
    page = client.get(
        _learning(organization_id) + f"?status=approved_for_reuse&source_finding_id={finding.id}"
    ).json()
    assert page["total"] == 1


def test_invalid_transitions_and_economic_basis_are_rejected(
    client: TestClient, db: Session
) -> None:
    organization_id, actor = make_org(db, "p310-immature")
    finding = _finding(db, organization_id, "IMMATURE")
    response = client.post(
        _learning(organization_id),
        json={
            "learning_type": "operational_pattern",
            "title": "Unsupported lesson",
            "statement": "A completed action must not be fabricated.",
            "scope": "Single case",
            "source_finding_ids": [str(finding.id)],
            "value_basis": "realized_measurement",
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "LEARNING_CASE_INELIGIBLE"
    learning = OperationalLearning(
        organization_id=organization_id,
        learning_type="operational_pattern",
        title="Candidate",
        statement="Candidate only",
        scope="Single case",
        status="candidate",
        provenance_type="manual",
        value_basis="none",
        created_by_user_id=actor,
    )
    db.add(learning)
    db.commit()
    invalid = client.post(
        _learning(organization_id, f"/{learning.id}/approve"),
        json={"transition": "approve", "rationale": "Cannot skip review."},
    )
    assert invalid.status_code == 409
    assert invalid.json()["detail"]["code"] == "INVALID_LEARNING_TRANSITION"


def test_simulation_provenance_is_explicit_and_tenant_scoped(
    client: TestClient, db: Session
) -> None:
    organization_id, actor = make_org(db, "p310-simulation")
    finding = _finding(db, organization_id, "SIMULATION")
    learning = OperationalLearning(
        organization_id=organization_id,
        learning_type="operational_pattern",
        title="Simulation-derived candidate",
        statement="Validation Laboratory observation only.",
        scope="Synthetic scenario",
        status="candidate",
        provenance_type="simulation",
        value_basis="none",
        created_by_user_id=actor,
    )
    db.add(learning)
    db.flush()
    db.add(
        LearningSourceCase(
            organization_id=organization_id,
            learning_id=learning.id,
            finding_id=finding.id,
            provenance_type="simulation",
        )
    )
    db.commit()
    page = client.get(_learning(organization_id) + "?provenance=simulation").json()
    assert page["total"] == 1
    assert page["items"][0]["provenance_type"] == "simulation"
    assert page["items"][0]["status"] == "candidate"
    foreign_id, _ = make_org(db, "p310-simulation-foreign")
    assert client.get(_learning(foreign_id, f"/{learning.id}")).status_code == 404
    db.add(
        LearningSourceCase(
            organization_id=foreign_id,
            learning_id=learning.id,
            finding_id=finding.id,
            provenance_type="simulation",
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
