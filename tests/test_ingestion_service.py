from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.models.ingestion import (
    DatasetStatus,
    DatasetVersionStatus,
    IngestionBatchStatus,
)
from app.models.source_system import SourceSystem
from app.schemas.contracts import OrganizationCreate
from app.schemas.ingestion import (
    DatasetCreate,
    DatasetUpdate,
    DatasetVersionCountsUpdate,
    DatasetVersionCreate,
    IngestionBatchCreate,
)
from app.schemas.source_systems import SourceSystemCreate
from app.services.ingestion_service import (
    DatasetService,
    DatasetVersionService,
    IngestionBatchService,
    IngestionConflictError,
    IngestionTenantMismatchError,
    InvalidIngestionTransitionError,
)
from app.services.organization_service import OrganizationService
from app.services.source_system_service import SourceSystemService


def foundation(db: Session, slug: str) -> tuple[UUID, UUID]:
    organization = OrganizationService().create(
        db,
        OrganizationCreate(
            name=slug,
            slug=slug,
            country_code="US",
            default_currency="USD",
            timezone="UTC",
        ),
    )
    source = SourceSystemService().create(
        db,
        organization.id,
        SourceSystemCreate(
            name="ERP",
            code="erp",
            system_type="erp",
            integration_method="api",
        ),
        uuid4(),
    )
    source.status = "active"
    db.commit()
    return organization.id, source.id


def batch_payload(source_id: UUID, number: str = "batch-001") -> IngestionBatchCreate:
    return IngestionBatchCreate(
        source_system_id=source_id,
        batch_number=number,
        ingestion_method="file_upload",
        trigger_type="manual",
        idempotency_key=f"key-{number}",
        manifest_metadata={"file_count": 1},
    )


def dataset_payload(source_id: UUID, code: str = "invoices") -> DatasetCreate:
    return DatasetCreate(
        source_system_id=source_id,
        name="Invoices",
        code=code,
        domain="invoices",
        dataset_type="transactional",
        default_timezone="America/Chicago",
        default_currency="usd",
        metadata_json={"owner": "finance"},
    )


def test_ingestion_validation_rejects_unsafe_and_inconsistent_values() -> None:
    source_id = uuid4()
    with pytest.raises(ValidationError):
        IngestionBatchCreate(
            source_system_id=source_id,
            batch_number="batch-secret",
            ingestion_method="file_upload",
            trigger_type="manual",
            manifest_metadata={"nested": {"access_token": "not-logged"}},
        )
    with pytest.raises(ValidationError):
        IngestionBatchCreate(
            source_system_id=source_id,
            batch_number="batch-period",
            ingestion_method="file_upload",
            trigger_type="manual",
            source_period_start="2026-02-02T00:00:00Z",
            source_period_end="2026-01-01T00:00:00Z",
        )
    with pytest.raises(ValidationError):
        DatasetVersionCreate(
            ingestion_batch_id=uuid4(),
            source_file_name="../unsafe.csv",
        )
    with pytest.raises(ValidationError):
        DatasetVersionCountsUpdate(
            record_count=10,
            accepted_record_count=8,
            rejected_record_count=3,
        )


def test_batch_idempotency_tenant_scope_and_lifecycle(db: Session) -> None:
    organization_id, source_id = foundation(db, "batch-service")
    other_id, _ = foundation(db, "batch-service-other")
    service = IngestionBatchService()
    payload = batch_payload(source_id)
    batch = service.create(db, organization_id, payload, uuid4())
    assert batch.status == IngestionBatchStatus.RECEIVED.value
    assert service.create(db, organization_id, payload, uuid4()).id == batch.id

    conflicting = payload.model_copy(update={"batch_number": "batch-002"})
    with pytest.raises(IngestionConflictError):
        service.create(db, organization_id, conflicting, uuid4())
    with pytest.raises(IngestionTenantMismatchError):
        service.create(db, other_id, batch_payload(source_id, "batch-other"), uuid4())

    service.transition(db, organization_id, batch.id, IngestionBatchStatus.QUEUED)
    validating = service.transition(db, organization_id, batch.id, IngestionBatchStatus.VALIDATING)
    assert validating.started_at is not None
    service.transition(db, organization_id, batch.id, IngestionBatchStatus.PROCESSING)
    completed = service.transition(db, organization_id, batch.id, IngestionBatchStatus.COMPLETED)
    assert completed.completed_at is not None
    with pytest.raises(InvalidIngestionTransitionError):
        service.retry(db, organization_id, batch.id)
    assert service.list(db, other_id) == []


def test_batch_failure_retry_quarantine_and_release(db: Session) -> None:
    organization_id, source_id = foundation(db, "batch-recovery")
    service = IngestionBatchService()
    failed = service.create(db, organization_id, batch_payload(source_id, "failure"), uuid4())
    service.transition(db, organization_id, failed.id, IngestionBatchStatus.VALIDATING)
    failed = service.record_failure(
        db, organization_id, failed.id, "VALIDATION_FAILED", "Validation failed"
    )
    assert failed.failed_at is not None
    assert service.retry(db, organization_id, failed.id).failed_at is None

    quarantined = service.create(
        db, organization_id, batch_payload(source_id, "quarantine"), uuid4()
    )
    service.transition(db, organization_id, quarantined.id, IngestionBatchStatus.VALIDATING)
    service.quarantine(db, organization_id, quarantined.id)
    assert service.release(db, organization_id, quarantined.id).status == "queued"


def test_dataset_lifecycle_duplicate_and_cross_tenant_source(db: Session) -> None:
    organization_id, source_id = foundation(db, "dataset-service")
    other_id, _ = foundation(db, "dataset-service-other")
    service = DatasetService()
    actor = uuid4()
    dataset = service.create(db, organization_id, dataset_payload(source_id), actor)
    assert dataset.default_currency == "USD"
    with pytest.raises(IngestionConflictError):
        service.create(db, organization_id, dataset_payload(source_id), actor)
    with pytest.raises(IngestionTenantMismatchError):
        service.create(db, other_id, dataset_payload(source_id, "cross"), actor)

    service.update(
        db,
        organization_id,
        dataset.id,
        DatasetUpdate(description="Governed invoices", schema_status="discovered"),
        actor,
    )
    service.transition(db, organization_id, dataset.id, DatasetStatus.ACTIVE, actor)
    service.transition(db, organization_id, dataset.id, DatasetStatus.PAUSED, actor)
    terminal = service.transition(
        db, organization_id, dataset.id, DatasetStatus.DECOMMISSIONED, actor
    )
    assert terminal.deactivated_at is not None
    with pytest.raises(InvalidIngestionTransitionError):
        service.transition(db, organization_id, dataset.id, DatasetStatus.ACTIVE, actor)


def test_dataset_versions_numbering_consistency_and_reconciliation(db: Session) -> None:
    organization_id, source_id = foundation(db, "version-service")
    batch_service = IngestionBatchService()
    dataset_service = DatasetService()
    version_service = DatasetVersionService(dataset_service, batch_service)
    dataset = dataset_service.create(db, organization_id, dataset_payload(source_id), uuid4())
    first_batch = batch_service.create(
        db, organization_id, batch_payload(source_id, "version-one"), uuid4()
    )
    second_batch = batch_service.create(
        db, organization_id, batch_payload(source_id, "version-two"), uuid4()
    )
    first = version_service.create(
        db,
        organization_id,
        dataset.id,
        DatasetVersionCreate(
            ingestion_batch_id=first_batch.id,
            source_file_name="invoices.csv",
            source_file_extension="csv",
        ),
    )
    assert first.version_number == 1
    with pytest.raises(IngestionConflictError):
        version_service.create(
            db,
            organization_id,
            dataset.id,
            DatasetVersionCreate(ingestion_batch_id=first_batch.id),
        )

    second = version_service.create(
        db,
        organization_id,
        dataset.id,
        DatasetVersionCreate(ingestion_batch_id=second_batch.id),
    )
    assert second.version_number == 2
    updated = version_service.update_counts(
        db,
        organization_id,
        dataset.id,
        first.id,
        DatasetVersionCountsUpdate(
            record_count=100,
            accepted_record_count=95,
            rejected_record_count=5,
            column_count=12,
        ),
    )
    batch = batch_service.get(db, organization_id, first_batch.id)
    assert (batch.actual_dataset_count, batch.actual_record_count) == (1, 100)
    assert (batch.accepted_record_count, batch.rejected_record_count) == (95, 5)
    version_service.transition(
        db,
        organization_id,
        dataset.id,
        updated.id,
        DatasetVersionStatus.VALIDATING,
    )
    version_service.transition(
        db,
        organization_id,
        dataset.id,
        updated.id,
        DatasetVersionStatus.ACCEPTED,
    )
    processed = version_service.transition(
        db,
        organization_id,
        dataset.id,
        updated.id,
        DatasetVersionStatus.PROCESSED,
    )
    assert processed.processed_at is not None
    with pytest.raises(InvalidIngestionTransitionError):
        version_service.update_counts(
            db,
            organization_id,
            dataset.id,
            processed.id,
            DatasetVersionCountsUpdate(
                record_count=1,
                accepted_record_count=1,
                rejected_record_count=0,
            ),
        )


@pytest.mark.parametrize("source_status", ["paused", "failed", "decommissioned"])
def test_source_lifecycle_blocks_new_downstream_but_preserves_history(
    db: Session, source_status: str
) -> None:
    organization_id, source_id = foundation(db, f"source-policy-{source_status}")
    batch_service = IngestionBatchService()
    existing = batch_service.create(
        db,
        organization_id,
        batch_payload(source_id, f"historical-{source_status}"),
        uuid4(),
    )
    source = db.get(SourceSystem, source_id)
    assert source is not None
    source.status = source_status
    db.commit()

    with pytest.raises(IngestionConflictError):
        batch_service.create(
            db,
            organization_id,
            batch_payload(source_id, f"blocked-{source_status}"),
            uuid4(),
        )
    with pytest.raises(IngestionConflictError):
        DatasetService().create(
            db,
            organization_id,
            dataset_payload(source_id, f"blocked-{source_status}"),
            uuid4(),
        )
    assert batch_service.get(db, organization_id, existing.id).id == existing.id


def test_source_lifecycle_check_remains_tenant_first(db: Session) -> None:
    owner_id, source_id = foundation(db, "source-policy-owner")
    other_id, _ = foundation(db, "source-policy-other")
    source = db.get(SourceSystem, source_id)
    assert source is not None
    source.status = "decommissioned"
    db.commit()
    with pytest.raises(IngestionTenantMismatchError):
        IngestionBatchService().create(
            db,
            other_id,
            batch_payload(source_id, "cross-tenant"),
            uuid4(),
        )
    assert owner_id != other_id
