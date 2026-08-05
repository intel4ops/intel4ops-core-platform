from conftest import IdentityState
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.schemas.contracts import OrganizationCreate
from app.services.organization_service import OrganizationService


def _make_org(db: Session, slug: str) -> str:
    organization = OrganizationService().create(
        db,
        OrganizationCreate(
            name=slug, slug=slug, country_code="US", default_currency="USD", timezone="UTC"
        ),
    )
    return str(organization.id)


def test_full_causal_workflow_via_api(client: TestClient, db: Session) -> None:
    method_response = client.post(
        "/api/v1/causal/methods",
        json={
            "method_code": "det_rule_api",
            "method_name": "Deterministic Rule",
            "method_class": "deterministic_temporal_rule",
            "method_version": "1.0.0",
            "default_confidence_weight": "0.8",
            "scope_type": "shared_core",
            "scope_key": "shared_core:det_rule_api",
        },
    )
    assert method_response.status_code == 201
    method_id = method_response.json()["id"]

    organization_id = _make_org(db, "causal-api-org")

    listed_methods = client.get(f"/api/v1/organizations/{organization_id}/causal/methods")
    assert listed_methods.status_code == 200
    assert any(m["method_code"] == "det_rule_api" for m in listed_methods.json())

    node_a = client.post(
        f"/api/v1/organizations/{organization_id}/causal/nodes",
        json={"node_type": "external_factor", "external_description": "cause"},
    )
    node_b = client.post(
        f"/api/v1/organizations/{organization_id}/causal/nodes",
        json={"node_type": "external_factor", "external_description": "effect"},
    )
    assert node_a.status_code == 201
    assert node_b.status_code == 201
    node_a_id = node_a.json()["id"]
    node_b_id = node_b.json()["id"]

    hypothesis = client.post(
        f"/api/v1/organizations/{organization_id}/causal/hypotheses",
        json={
            "source_node_id": node_a_id,
            "target_node_id": node_b_id,
            "proposed_edge_type": "causes",
            "method_id": method_id,
        },
    )
    assert hypothesis.status_code == 201
    hypothesis_id = hypothesis.json()["id"]
    assert hypothesis.json()["lifecycle_status"] == "draft"

    proposed = client.post(
        f"/api/v1/organizations/{organization_id}/causal/hypotheses/{hypothesis_id}/propose"
    )
    assert proposed.status_code == 200
    assert proposed.json()["lifecycle_status"] == "proposed"

    evidence = client.post(
        f"/api/v1/organizations/{organization_id}/causal/hypotheses/{hypothesis_id}/evidence",
        json={"evidence_kind": "rule_trace", "evidence_id": str(node_a_id), "supports": True},
    )
    assert evidence.status_code == 201

    evaluated = client.post(
        f"/api/v1/organizations/{organization_id}/causal/hypotheses/{hypothesis_id}/evaluate"
    )
    assert evaluated.status_code == 200
    assert evaluated.json()["hard_gate_outcome"] == "passed"
    assert evaluated.json()["lifecycle_status"] == "under_review"

    review = client.post(
        f"/api/v1/organizations/{organization_id}/causal/hypotheses/{hypothesis_id}/reviews",
        json={"decision": "confirm", "notes": "looks right"},
    )
    assert review.status_code == 201
    assert review.json()["resulting_lifecycle_status"] == "confirmed"

    fetched = client.get(
        f"/api/v1/organizations/{organization_id}/causal/hypotheses/{hypothesis_id}"
    )
    assert fetched.status_code == 200
    assert fetched.json()["lifecycle_status"] == "confirmed"

    ranking = client.get(f"/api/v1/organizations/{organization_id}/causal/root-causes")
    assert ranking.status_code == 200
    assert ranking.json() == []


def test_association_only_hypothesis_cannot_be_confirmed_via_api(
    client: TestClient, db: Session
) -> None:
    organization_id = _make_org(db, "causal-api-association")
    method_response = client.post(
        "/api/v1/causal/methods",
        json={
            "method_code": "det_rule_api2",
            "method_name": "Deterministic Rule",
            "method_class": "deterministic_temporal_rule",
            "method_version": "1.0.0",
            "default_confidence_weight": "0.8",
            "scope_type": "shared_core",
            "scope_key": "shared_core:det_rule_api2",
        },
    )
    method_id = method_response.json()["id"]
    node_a = client.post(
        f"/api/v1/organizations/{organization_id}/causal/nodes",
        json={"node_type": "external_factor", "external_description": "a"},
    ).json()
    node_b = client.post(
        f"/api/v1/organizations/{organization_id}/causal/nodes",
        json={"node_type": "external_factor", "external_description": "b"},
    ).json()
    hypothesis = client.post(
        f"/api/v1/organizations/{organization_id}/causal/hypotheses",
        json={
            "source_node_id": node_a["id"],
            "target_node_id": node_b["id"],
            "proposed_edge_type": "correlates_with",
            "method_id": method_id,
        },
    ).json()
    client.post(
        f"/api/v1/organizations/{organization_id}/causal/hypotheses/{hypothesis['id']}/propose"
    )
    client.post(
        f"/api/v1/organizations/{organization_id}/causal/hypotheses/{hypothesis['id']}/evidence",
        json={"evidence_kind": "rule_trace", "evidence_id": node_a["id"], "supports": True},
    )
    client.post(
        f"/api/v1/organizations/{organization_id}/causal/hypotheses/{hypothesis['id']}/evaluate"
    )
    review = client.post(
        f"/api/v1/organizations/{organization_id}/causal/hypotheses/{hypothesis['id']}/reviews",
        json={"decision": "confirm"},
    )
    assert review.status_code == 422
    assert review.json()["detail"]["code"] == "association_cannot_confirm"


def test_unauthenticated_request_is_rejected(
    client: TestClient, db: Session, identity: IdentityState
) -> None:
    organization_id = _make_org(db, "causal-api-auth")
    identity.user_id = None
    denied = client.get(f"/api/v1/organizations/{organization_id}/causal/methods")
    assert denied.status_code == 401


def test_validation_rejects_invalid_method_class(client: TestClient) -> None:
    response = client.post(
        "/api/v1/causal/methods",
        json={
            "method_code": "invalid_method",
            "method_name": "Invalid",
            "method_class": "not_a_real_method_class",
            "method_version": "1.0.0",
            "default_confidence_weight": "0.8",
            "scope_type": "shared_core",
            "scope_key": "shared_core:invalid_method",
        },
    )
    assert response.status_code == 422
