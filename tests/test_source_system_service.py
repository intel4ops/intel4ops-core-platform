from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.models.source_system import SourceHealthStatus, SourceSystemStatus
from app.schemas.contracts import OrganizationCreate
from app.schemas.source_systems import SourceSystemCreate, SourceSystemUpdate
from app.services.organization_service import OrganizationService
from app.services.source_system_service import (
    DuplicateSourceSystemCodeError,
    InvalidSourceSystemTransitionError,
    SourceSystemNotFoundError,
    SourceSystemOrganizationNotFoundError,
    SourceSystemService,
)


def create_organization(db: Session, slug: str = "source-service") -> UUID:
    return (
        OrganizationService()
        .create(
            db,
            OrganizationCreate(
                name=slug,
                slug=slug,
                country_code="US",
                default_currency="USD",
                timezone="UTC",
            ),
        )
        .id
    )


def payload(code: str = "primary-erp") -> SourceSystemCreate:
    return SourceSystemCreate(
        name=" Primary ERP ",
        code=code,
        system_type="erp",
        provider=" SAP ",
        integration_method="api",
        environment="production",
        base_url="https://erp.example.test",
        owner_email="owner@example.com",
        timezone="America/Chicago",
        currency="usd",
        credential_reference="vault://intel4ops/erp",
        configuration_metadata={"region": "us-central"},
        capabilities=["invoices", "vendors"],
    )


def test_validation_normalizes_and_rejects_secrets() -> None:
    validated = payload()
    assert validated.name == "Primary ERP"
    assert validated.provider == "sap"
    assert validated.currency == "USD"

    for invalid in (
        {"code": "NOT SAFE"},
        {"timezone": "Mars/Olympus"},
        {"base_url": "ftp://example.test"},
        {"owner_email": "not-an-email"},
        {"configuration_metadata": {"nested": [{"API_KEY": "not-logged"}]}},
    ):
        values = payload().model_dump()
        values.update(invalid)
        with pytest.raises(ValidationError):
            SourceSystemCreate.model_validate(values)


def test_create_duplicate_tenant_scope_and_updates(db: Session) -> None:
    service = SourceSystemService()
    first_id = create_organization(db)
    second_id = create_organization(db, "source-service-second")
    actor = uuid4()
    source = service.create(db, first_id, payload(), actor)
    assert source.created_by_user_id == actor
    assert source.updated_by_user_id == actor
    assert source.status == SourceSystemStatus.DRAFT.value

    with pytest.raises(DuplicateSourceSystemCodeError):
        service.create(db, first_id, payload(), actor)
    service.create(db, second_id, payload(), actor)
    with pytest.raises(SourceSystemNotFoundError):
        service.get(db, second_id, source.id)
    with pytest.raises(SourceSystemOrganizationNotFoundError):
        service.create(db, uuid4(), payload("missing-org"), actor)

    updated = service.update(
        db,
        first_id,
        source.id,
        SourceSystemUpdate(name="Renamed", status=SourceSystemStatus.CONFIGURED),
        uuid4(),
    )
    assert updated.name == "Renamed"
    assert updated.status == SourceSystemStatus.CONFIGURED.value
    assert service.list(db, first_id, provider="SAP", search="rename") == [updated]


def test_lifecycle_connection_health_and_terminal_state(db: Session) -> None:
    service = SourceSystemService()
    organization_id = create_organization(db, "source-lifecycle")
    actor = uuid4()
    source = service.create(db, organization_id, payload("lifecycle"), actor)

    service.update(
        db,
        organization_id,
        source.id,
        SourceSystemUpdate(status=SourceSystemStatus.CONFIGURED),
        actor,
    )
    service.update(
        db,
        organization_id,
        source.id,
        SourceSystemUpdate(status=SourceSystemStatus.VALIDATING),
        actor,
    )
    success = service.record_connection_success(db, organization_id, source.id, actor)
    assert success.status == SourceSystemStatus.ACTIVE.value
    assert success.health_status == SourceHealthStatus.HEALTHY.value
    assert success.failure_count == 0
    assert success.last_connection_success_at is not None

    for expected_count in range(1, 4):
        failed = service.record_connection_failure(db, organization_id, source.id, actor)
        assert failed.failure_count == expected_count
    assert failed.health_status == SourceHealthStatus.UNHEALTHY.value

    paused = service.pause(db, organization_id, source.id, actor)
    assert paused.status == SourceSystemStatus.PAUSED.value
    assert service.reactivate(db, organization_id, source.id, actor).status == "active"
    terminal = service.decommission(db, organization_id, source.id, actor)
    assert terminal.status == SourceSystemStatus.DECOMMISSIONED.value
    assert terminal.is_active is False
    assert terminal.deactivated_at is not None
    with pytest.raises(InvalidSourceSystemTransitionError):
        service.reactivate(db, organization_id, source.id, actor)
    with pytest.raises(InvalidSourceSystemTransitionError):
        service.record_connection_failure(db, organization_id, source.id, actor)
    with pytest.raises(InvalidSourceSystemTransitionError):
        service.update(
            db,
            organization_id,
            source.id,
            SourceSystemUpdate(name="Identity cannot change"),
            actor,
        )
    administrative = service.update(
        db,
        organization_id,
        source.id,
        SourceSystemUpdate(description="Retained historical source", owner_name="Records"),
        actor,
    )
    assert administrative.description == "Retained historical source"


def test_invalid_transition_is_rejected(db: Session) -> None:
    service = SourceSystemService()
    organization_id = create_organization(db, "invalid-transition")
    source = service.create(db, organization_id, payload("invalid-transition"), uuid4())
    with pytest.raises(InvalidSourceSystemTransitionError):
        service.pause(db, organization_id, source.id, uuid4())
