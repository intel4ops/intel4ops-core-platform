from fastapi.testclient import TestClient


def organization_payload(slug: str = "acme-transit") -> dict[str, object]:
    return {
        "name": "Acme Transit",
        "slug": slug,
        "legal_name": "Acme Transit LLC",
        "industry": "transportation",
        "country_code": "us",
        "default_currency": "usd",
        "timezone": "America/Chicago",
        "description": "Regional transit operator",
        "is_demo": False,
    }


def test_organization_crud_and_deactivate(client: TestClient) -> None:
    created = client.post("/api/v1/organizations", json=organization_payload())
    assert created.status_code == 201
    body = created.json()
    organization_id = body["id"]
    assert body["country_code"] == "US"
    assert body["default_currency"] == "USD"
    assert body["status"] == "active"

    fetched = client.get(f"/api/v1/organizations/{organization_id}")
    assert fetched.status_code == 200
    assert fetched.json()["slug"] == "acme-transit"

    listed = client.get("/api/v1/organizations")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [organization_id]

    updated = client.patch(
        f"/api/v1/organizations/{organization_id}",
        json={"name": "Acme Regional Transit", "default_currency": "cad"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Acme Regional Transit"
    assert updated.json()["default_currency"] == "CAD"

    deactivated = client.post(f"/api/v1/organizations/{organization_id}/deactivate")
    assert deactivated.status_code == 200
    assert deactivated.json()["status"] == "inactive"


def test_duplicate_slug_returns_conflict(client: TestClient) -> None:
    assert client.post("/api/v1/organizations", json=organization_payload()).status_code == 201
    duplicate = client.post("/api/v1/organizations", json=organization_payload())
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "Organization slug already exists"


def test_organization_validation(client: TestClient) -> None:
    for field, value in [
        ("slug", "Not Valid"),
        ("country_code", "USA"),
        ("country_code", "1A"),
        ("default_currency", "US"),
        ("default_currency", "12$"),
    ]:
        payload = organization_payload()
        payload[field] = value
        response = client.post("/api/v1/organizations", json=payload)
        assert response.status_code == 422


def test_missing_organization_returns_not_found(client: TestClient) -> None:
    response = client.get("/api/v1/organizations/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


def test_update_rejects_null_for_required_fields(client: TestClient) -> None:
    created = client.post("/api/v1/organizations", json=organization_payload())
    organization_id = created.json()["id"]

    for field in ["name", "slug", "country_code", "default_currency", "timezone"]:
        response = client.patch(
            f"/api/v1/organizations/{organization_id}",
            json={field: None},
        )
        assert response.status_code == 422
