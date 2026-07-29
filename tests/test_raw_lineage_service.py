from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.models.raw_lineage import (
    LineageEventType,
    LineageNodeType,
    LineageRelationshipType,
    ProcessingRunStatus,
    RawObjectStatus,
    RawRecordStatus,
)
from app.models.source_system import SourceSystem
from app.schemas.contracts import OrganizationCreate
from app.schemas.ingestion import DatasetCreate, DatasetVersionCreate, IngestionBatchCreate
from app.schemas.raw_lineage import (
    IntegrityVerification,
    LineageEdgeCreate,
    LineageNodeCreate,
    ProcessingRunCreate,
    ProcessingRunFailure,
    ProcessingRunResult,
    RawRecordReferenceCreate,
    RawStorageObjectCreate,
)
from app.schemas.source_systems import SourceSystemCreate
from app.services.ingestion_service import (
    DatasetService,
    DatasetVersionService,
    IngestionBatchService,
)
from app.services.organization_service import OrganizationService
from app.services.raw_lineage_service import (
    LineageEventService,
    LineageService,
    ProcessingRunService,
    RawLineageConflictError,
    RawLineageTenantMismatchError,
    RawRecordReferenceService,
    RawStorageObjectService,
)
from app.services.source_system_service import SourceSystemService


def foundation(db: Session, slug: str) -> tuple[UUID, UUID, UUID, UUID, UUID]:
    actor = uuid4()
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
            integration_method="file_upload",
        ),
        actor,
    )
    source.status = "active"
    db.commit()
    batch = IngestionBatchService().create(
        db,
        organization.id,
        IngestionBatchCreate(
            source_system_id=source.id,
            batch_number="batch-001",
            ingestion_method="file_upload",
            trigger_type="manual",
        ),
        actor,
    )
    dataset = DatasetService().create(
        db,
        organization.id,
        DatasetCreate(
            source_system_id=source.id,
            name="Invoices",
            code="invoices",
            domain="invoices",
            dataset_type="transactional",
        ),
        actor,
    )
    version = DatasetVersionService().create(
        db,
        organization.id,
        dataset.id,
        DatasetVersionCreate(
            ingestion_batch_id=batch.id,
            source_file_name="invoices.csv",
            source_file_extension="csv",
        ),
    )
    return organization.id, source.id, batch.id, dataset.id, version.id


def raw_payload(source_id: UUID, batch_id: UUID, version_id: UUID) -> RawStorageObjectCreate:
    return RawStorageObjectCreate(
        source_system_id=source_id,
        ingestion_batch_id=batch_id,
        dataset_version_id=version_id,
        object_number="raw-001",
        idempotency_key="raw-key-001",
        object_type="file",
        storage_provider="s3",
        storage_reference="s3://opaque-reference/object-001",
        original_filename="invoices.csv",
        normalized_filename="invoices.csv",
        file_extension="csv",
        media_type="text/csv",
        encoding="utf-8",
        content_checksum_algorithm="sha256",
        content_checksum="a" * 64,
        size_bytes=128,
        received_at=datetime.now(UTC),
        metadata_json={"classification": "internal"},
    )


def test_validation_rejects_secret_references_checksums_and_unsafe_metadata() -> None:
    source_id, batch_id, version_id = uuid4(), uuid4(), uuid4()
    base = raw_payload(source_id, batch_id, version_id)
    with pytest.raises(ValidationError, match="Storage reference is not permitted"):
        RawStorageObjectCreate(
            **{
                **base.model_dump(),
                "storage_reference": "https://bucket/item?X-Amz-Signature=hidden",
            }
        )
    with pytest.raises(ValidationError, match="64 hexadecimal"):
        RawStorageObjectCreate(**{**base.model_dump(), "content_checksum": "bad"})
    with pytest.raises(ValidationError):
        RawStorageObjectCreate(
            **{**base.model_dump(), "metadata_json": {"nested": {"access_token": "hidden"}}}
        )


def test_raw_object_idempotency_tenant_context_and_automatic_lineage(db: Session) -> None:
    organization_id, source_id, batch_id, _, version_id = foundation(db, "raw-register")
    actor = uuid4()
    service = RawStorageObjectService()
    payload = raw_payload(source_id, batch_id, version_id)
    raw_object = service.register(db, organization_id, payload, actor)
    assert service.register(db, organization_id, payload, actor).id == raw_object.id
    assert service.list(db, organization_id) == [raw_object]

    graph = service.lineage.graph(
        db,
        organization_id,
        service.lineage.node_for_entity(
            db, organization_id, LineageNodeType.RAW_STORAGE_OBJECT, raw_object.id
        ).id,
        direction="upstream",
    )
    assert {node.node_type for node in graph.nodes} >= {
        "source_system",
        "ingestion_batch",
        "dataset",
        "dataset_version",
        "raw_storage_object",
    }
    assert len(graph.edges) == 4

    source = db.get(SourceSystem, source_id)
    assert source is not None
    source.status = "paused"
    db.commit()
    assert service.register(db, organization_id, payload, actor).id == raw_object.id
    with pytest.raises(RawLineageConflictError):
        service.register(
            db,
            organization_id,
            payload.model_copy(
                update={"object_number": "raw-002", "idempotency_key": "raw-key-002"}
            ),
            actor,
        )

    other_id, _, _, _, _ = foundation(db, "raw-register-other")
    with pytest.raises(RawLineageTenantMismatchError):
        service.register(
            db,
            other_id,
            payload.model_copy(update={"object_number": "cross", "idempotency_key": "cross"}),
            actor,
        )


def test_integrity_lifecycle_legal_hold_and_terminal_state(db: Session) -> None:
    organization_id, source_id, batch_id, _, version_id = foundation(db, "raw-lifecycle")
    actor = uuid4()
    service = RawStorageObjectService()
    item = service.register(
        db, organization_id, raw_payload(source_id, batch_id, version_id), actor
    )
    service.transition(db, organization_id, item.id, RawObjectStatus.RECEIVED, actor)
    service.transition(db, organization_id, item.id, RawObjectStatus.VERIFYING, actor)
    with pytest.raises(RawLineageConflictError, match="verified"):
        service.transition(db, organization_id, item.id, RawObjectStatus.SEALED, actor)
    verified = service.verify(
        db,
        organization_id,
        item.id,
        IntegrityVerification(checksum_algorithm="sha256", checksum="a" * 64, matched=True),
        actor,
    )
    assert verified.verified_at is not None
    sealed = service.transition(db, organization_id, item.id, RawObjectStatus.SEALED, actor)
    assert sealed.sealed_at is not None
    service.apply_legal_hold(db, organization_id, item.id, "Regulatory review", actor)
    with pytest.raises(RawLineageConflictError, match="Legal hold"):
        service.transition(db, organization_id, item.id, RawObjectStatus.DELETION_REQUESTED, actor)
    service.release_legal_hold(db, organization_id, item.id, actor)
    service.transition(db, organization_id, item.id, RawObjectStatus.DELETION_REQUESTED, actor)
    deleted = service.transition(
        db, organization_id, item.id, RawObjectStatus.DELETED_REFERENCE, actor
    )
    with pytest.raises(RawLineageConflictError):
        service.transition(db, organization_id, deleted.id, RawObjectStatus.ARCHIVED, actor)


def test_integrity_mismatch_prevents_sealing_and_is_audited(db: Session) -> None:
    organization_id, source_id, batch_id, _, version_id = foundation(db, "raw-mismatch")
    actor = uuid4()
    service = RawStorageObjectService()
    item = service.register(
        db, organization_id, raw_payload(source_id, batch_id, version_id), actor
    )
    service.transition(db, organization_id, item.id, RawObjectStatus.RECEIVED, actor)
    service.transition(db, organization_id, item.id, RawObjectStatus.VERIFYING, actor)
    result = service.verify(
        db,
        organization_id,
        item.id,
        IntegrityVerification(checksum_algorithm="sha256", checksum="b" * 64, matched=False),
        actor,
    )
    assert result.integrity_status == "mismatch"
    assert LineageEventType.INTEGRITY_MISMATCH.value in {
        event.event_type for event in service.events.list(db, organization_id)
    }


def test_record_references_are_bounded_consistent_and_traced(db: Session) -> None:
    organization_id, source_id, batch_id, _, version_id = foundation(db, "raw-records")
    actor = uuid4()
    raw_service = RawStorageObjectService()
    item = raw_service.register(
        db, organization_id, raw_payload(source_id, batch_id, version_id), actor
    )
    service = RawRecordReferenceService(raw_service, raw_service.lineage, raw_service.events)
    reference = service.register(
        db,
        organization_id,
        item.id,
        RawRecordReferenceCreate(
            dataset_version_id=version_id,
            record_sequence=1,
            source_row_number=2,
            record_checksum_algorithm="md5",
            record_checksum="f" * 32,
        ),
        actor,
    )
    assert (
        service.set_status(db, organization_id, reference.id, RawRecordStatus.EXCLUDED).status
        == "excluded"
    )
    graph = service.lineage.graph(
        db,
        organization_id,
        service.lineage.node_for_entity(
            db, organization_id, LineageNodeType.RAW_STORAGE_OBJECT, item.id
        ).id,
        direction="downstream",
    )
    assert any(edge.relationship_type == "contains" for edge in graph.edges)
    with pytest.raises(RawLineageTenantMismatchError):
        service.register(
            db,
            organization_id,
            item.id,
            RawRecordReferenceCreate(dataset_version_id=uuid4(), record_sequence=2),
            actor,
        )
    with pytest.raises(RawLineageConflictError):
        service.register_batch(db, organization_id, item.id, [], actor)


def test_processing_run_lifecycle_counts_and_events(db: Session) -> None:
    organization_id, _, batch_id, _, version_id = foundation(db, "processing-run")
    actor = uuid4()
    service = ProcessingRunService()
    run = service.create(
        db,
        organization_id,
        ProcessingRunCreate(
            ingestion_batch_id=batch_id,
            dataset_version_id=version_id,
            run_type="integrity_verification",
            executor_type="worker",
            parameters_json={"mode": "checksum"},
        ),
        actor,
    )
    run_node = service.lineage.node_for_entity(
        db, organization_id, LineageNodeType.PROCESSING_RUN, run.id
    )
    graph = service.lineage.graph(db, organization_id, run_node.id, direction="upstream")
    assert {edge.relationship_type for edge in graph.edges} == {
        LineageRelationshipType.CONSUMED_BY.value
    }
    started = service.transition(db, organization_id, run.id, ProcessingRunStatus.RUNNING, actor)
    assert started.started_at is not None
    completed = service.transition(
        db,
        organization_id,
        run.id,
        ProcessingRunStatus.COMPLETED,
        actor,
        ProcessingRunResult(input_count=1, output_count=1),
    )
    assert completed.completed_at is not None
    with pytest.raises(RawLineageConflictError):
        service.transition(db, organization_id, run.id, ProcessingRunStatus.RUNNING, actor)

    failed = service.create(
        db,
        organization_id,
        ProcessingRunCreate(
            ingestion_batch_id=batch_id,
            run_type="parsing",
            executor_type="worker",
        ),
        actor,
    )
    service.transition(db, organization_id, failed.id, ProcessingRunStatus.RUNNING, actor)
    failed = service.fail(
        db,
        organization_id,
        failed.id,
        ProcessingRunFailure(
            failure_code="PARSE",
            failure_summary="Parser rejected the input",
            error_count=1,
        ),
        actor,
    )
    assert failed.failed_at is not None
    assert (
        service.transition(db, organization_id, failed.id, ProcessingRunStatus.QUEUED, actor).status
        == "queued"
    )
    with pytest.raises(ValidationError):
        ProcessingRunCreate(run_type="mapping", executor_type="worker")
    infrastructure = service.create(
        db,
        organization_id,
        ProcessingRunCreate(run_type="custom", executor_type="worker"),
        actor,
    )
    assert infrastructure.ingestion_batch_id is None


def test_lineage_duplicate_edges_cycle_prevention_and_tenant_scope(db: Session) -> None:
    organization_id, source_id, batch_id, _, _ = foundation(db, "lineage-graph")
    actor = uuid4()
    service = LineageService()
    source = service.register_node(
        db,
        organization_id,
        LineageNodeCreate(node_type="source_system", entity_id=source_id),
    )
    batch = service.register_node(
        db,
        organization_id,
        LineageNodeCreate(node_type="ingestion_batch", entity_id=batch_id),
    )
    forward = service.create_edge(
        db,
        organization_id,
        LineageEdgeCreate(
            from_node_id=source.id,
            to_node_id=batch.id,
            relationship_type=LineageRelationshipType.DERIVED_FROM,
        ),
        actor,
    )
    repeated = service.create_edge(
        db,
        organization_id,
        LineageEdgeCreate(
            from_node_id=source.id,
            to_node_id=batch.id,
            relationship_type=LineageRelationshipType.DERIVED_FROM,
        ),
        actor,
    )
    assert repeated.id == forward.id
    with pytest.raises(RawLineageConflictError, match="cycle"):
        service.create_edge(
            db,
            organization_id,
            LineageEdgeCreate(
                from_node_id=batch.id,
                to_node_id=source.id,
                relationship_type=LineageRelationshipType.DERIVED_FROM,
            ),
            actor,
        )
    other_id, _, _, _, _ = foundation(db, "lineage-graph-other")
    with pytest.raises(RawLineageTenantMismatchError):
        service.register_node(
            db,
            other_id,
            LineageNodeCreate(node_type="source_system", entity_id=source_id),
        )


def test_events_are_tenant_scoped_and_append_only(db: Session) -> None:
    organization_id, source_id, _, _, _ = foundation(db, "lineage-events")
    other_id, _, _, _, _ = foundation(db, "lineage-events-other")
    actor = uuid4()
    events = LineageEventService()
    events.record(
        db,
        organization_id,
        LineageEventType.REGISTERED,
        "source_system",
        source_id,
        actor,
    )
    db.commit()
    assert len(events.list(db, organization_id)) == 1
    assert events.list(db, other_id) == []
