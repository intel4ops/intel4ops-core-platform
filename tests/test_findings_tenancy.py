from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Finding, Organization
from app.schemas.contracts import FindingCreate, OrganizationCreate
from app.services.finding_service import FindingService
from app.services.organization_service import OrganizationService


def create_organization(db: Session, slug: str) -> Organization:
    return OrganizationService().create(
        db,
        OrganizationCreate(
            name=slug.title(),
            slug=slug,
            country_code="US",
            default_currency="USD",
            timezone="UTC",
        ),
    )


def finding_payload(title: str) -> FindingCreate:
    return FindingCreate(
        rule_id="TEST-001",
        title=title,
        summary="Tenant-scoping test",
        domain="maintenance",
        exposure_low=10,
        exposure_high=20,
        confidence_score=0.8,
        evidence=[
            {
                "source_system": "test",
                "source_record_id": "row-1",
                "evidence_type": "test_record",
                "payload": {"asset_id": "A1"},
            }
        ],
    )


def test_findings_are_created_and_listed_by_organization(db: Session) -> None:
    first = create_organization(db, "first-org")
    second = create_organization(db, "second-org")
    service = FindingService()
    service.create(db, first.id, finding_payload("First finding"))
    service.create(db, second.id, finding_payload("Second finding"))

    assert [item.title for item in service.list(db, first.id)] == ["First finding"]
    assert [item.title for item in service.list(db, second.id)] == ["Second finding"]
    persisted = list(db.scalars(select(Finding)).all())
    assert {item.organization_id for item in persisted} == {first.id, second.id}
    assert all(item.evidence[0].organization_id == item.organization_id for item in persisted)


def test_findings_api_requires_and_honors_organization_scope(client: TestClient) -> None:
    first = client.post(
        "/api/v1/organizations",
        json={
            "name": "First",
            "slug": "first",
            "country_code": "US",
            "default_currency": "USD",
            "timezone": "UTC",
        },
    ).json()
    second = client.post(
        "/api/v1/organizations",
        json={
            "name": "Second",
            "slug": "second",
            "country_code": "US",
            "default_currency": "USD",
            "timezone": "UTC",
        },
    ).json()

    assert client.get("/api/v1/command/findings").status_code == 422
    first_response = client.get("/api/v1/command/findings", params={"organization_id": first["id"]})
    second_response = client.get(
        "/api/v1/command/findings", params={"organization_id": second["id"]}
    )
    assert first_response.json() == []
    assert second_response.json() == []
    assert UUID(first["id"]) != UUID(second["id"])
