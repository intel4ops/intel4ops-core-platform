from uuid import uuid4

from conftest import IdentityState
from fastapi.testclient import TestClient


def test_decision_method_catalog_lists_bounded_methods(client: TestClient) -> None:
    response = client.get("/api/v1/decision-methods")
    assert response.status_code == 200
    methods = {item["method_code"] for item in response.json()}
    assert "scipy_milp_portfolio" in methods
    assert "scipy_hungarian_assignment" in methods
    assert "python_critical_path" in methods
    assert all("genetic" not in method for method in methods)


def test_decision_catalog_does_not_require_tenant_context(
    client: TestClient, identity: IdentityState
) -> None:
    identity.user_id = uuid4()
    identity.is_platform_admin = False
    response = client.get("/api/v1/decision-methods")
    assert response.status_code == 200


def test_tenant_decision_endpoint_fails_closed_without_identity(
    client: TestClient, identity: IdentityState
) -> None:
    identity.user_id = None
    response = client.get(f"/api/v1/organizations/{uuid4()}/decisions/history")
    assert response.status_code == 401
