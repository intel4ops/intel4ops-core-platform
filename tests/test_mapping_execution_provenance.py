from __future__ import annotations

import inspect
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_canonical_mapping_foundation import (
    discovered_schema,
    foundation,
    published_entity_mapping,
)

from app.models.canonical_mapping import MappingRun, SourceField
from app.models.ingestion import Dataset
from app.models.operational_memory import OperationalMemoryItem
from app.models.trust import TrustAssessment
from app.schemas.canonical_mapping import MappingInputRecord, MappingRunCreate
from app.schemas.ingestion import DatasetVersionCreate, IngestionBatchCreate
from app.services.canonical_mapping_service import (
    CanonicalMappingServiceError,
    mapping_execution_service,
)
from app.services.ingestion_service import DatasetVersionService, IngestionBatchService


def second_dataset_version(
    db: Session, organization_id: UUID, dataset_id: UUID, actor: UUID, slug: str
) -> UUID:
    dataset = db.get(Dataset, dataset_id)
    assert dataset is not None
    batch = IngestionBatchService().create(
        db,
        organization_id,
        IngestionBatchCreate(
            source_system_id=dataset.source_system_id,
            batch_number=f"batch-{slug}",
            ingestion_method="file_upload",
            trigger_type="manual",
        ),
        actor,
    )
    version = DatasetVersionService().create(
        db,
        organization_id,
        dataset_id,
        DatasetVersionCreate(
            ingestion_batch_id=batch.id,
            source_file_name=f"{slug}.csv",
            source_file_extension="csv",
        ),
    )
    return version.id


def _request(
    dataset_version_id: UUID,
    template_version_id: UUID,
    source_schema_id: UUID,
    idempotency_key: str,
    raw_reference_id: UUID,
) -> MappingRunCreate:
    return MappingRunCreate(
        dataset_version_id=dataset_version_id,
        template_version_id=template_version_id,
        source_schema_id=source_schema_id,
        idempotency_key=idempotency_key,
        records=[
            MappingInputRecord(
                raw_record_reference_id=raw_reference_id,
                values={"customer_id": "C-100", "customer_name": "Acme"},
            )
        ],
    )


def test_source_schema_id_is_required_on_mapping_run_create() -> None:
    with pytest.raises(ValidationError):
        MappingRunCreate(  # type: ignore[call-arg]
            dataset_version_id=uuid4(),
            template_version_id=uuid4(),
            idempotency_key="missing-schema",
        )


def test_valid_same_tenant_schema_is_accepted_and_persisted(db: Session) -> None:
    organization_id, actor, dataset_id, version_id, _, raw_reference_id = foundation(
        db, "cm01-valid"
    )
    _, template_version = published_entity_mapping(db, organization_id, actor)
    schema = discovered_schema(db, organization_id, dataset_id, version_id, "cm01-valid")
    run = mapping_execution_service.execute(
        db,
        organization_id,
        _request(version_id, template_version.id, schema.id, "cm01-valid-run", raw_reference_id),
        actor,
    )
    assert run.source_schema_id == schema.id
    assert run.schema_fingerprint_snapshot == schema.schema_fingerprint
    assert run.schema_fingerprint_snapshot != template_version.content_hash


def test_nonexistent_source_schema_is_rejected(db: Session) -> None:
    organization_id, actor, _, version_id, _, raw_reference_id = foundation(db, "cm01-missing")
    _, template_version = published_entity_mapping(db, organization_id, actor)
    with pytest.raises(CanonicalMappingServiceError) as exc:
        mapping_execution_service.execute(
            db,
            organization_id,
            _request(
                version_id, template_version.id, uuid4(), "cm01-missing-run", raw_reference_id
            ),
            actor,
        )
    assert (exc.value.code, exc.value.status) == ("SOURCE_SCHEMA_NOT_FOUND", 404)


def test_cross_tenant_source_schema_is_safe_not_found(db: Session) -> None:
    organization_id, actor, _, version_id, _, raw_reference_id = foundation(db, "cm01-tenant-a")
    other_id, _, other_dataset_id, other_version_id, _, _ = foundation(db, "cm01-tenant-b")
    _, template_version = published_entity_mapping(db, organization_id, actor)
    other_schema = discovered_schema(
        db, other_id, other_dataset_id, other_version_id, "cm01-tenant-b"
    )
    with pytest.raises(CanonicalMappingServiceError) as exc:
        mapping_execution_service.execute(
            db,
            organization_id,
            _request(
                version_id,
                template_version.id,
                other_schema.id,
                "cm01-cross-tenant-run",
                raw_reference_id,
            ),
            actor,
        )
    assert (exc.value.code, exc.value.status) == ("SOURCE_SCHEMA_NOT_FOUND", 404)


def test_direct_sql_rejects_cross_tenant_source_schema_reference(db: Session) -> None:
    organization_id, actor, _, version_id, _, _ = foundation(db, "cm01-fk-a")
    other_id, _, other_dataset_id, other_version_id, _, _ = foundation(db, "cm01-fk-b")
    _, template_version = published_entity_mapping(db, organization_id, actor)
    other_schema = discovered_schema(db, other_id, other_dataset_id, other_version_id, "cm01-fk-b")
    with pytest.raises(IntegrityError):
        db.execute(
            text(
                """
                INSERT INTO mapping_runs (
                    id, organization_id, dataset_version_id, template_version_id,
                    source_schema_id, status, idempotency_key, request_fingerprint,
                    input_count, mapped_count, exception_count, rejected_count,
                    created_by_user_id, created_at, updated_at
                ) VALUES (
                    :id, :organization_id, :dataset_version_id, :template_version_id,
                    :source_schema_id, 'created', 'cm01-fk-violation', :fingerprint,
                    0, 0, 0, 0, :actor, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            ),
            {
                "id": str(uuid4()),
                "organization_id": str(organization_id),
                "dataset_version_id": str(version_id),
                "template_version_id": str(template_version.id),
                "source_schema_id": str(other_schema.id),
                "fingerprint": "1" * 64,
                "actor": str(actor),
            },
        )
        db.commit()
    db.rollback()


def test_schema_from_wrong_dataset_version_is_rejected(db: Session) -> None:
    organization_id, actor, dataset_id, version_id, _, raw_reference_id = foundation(
        db, "cm01-wrong-version"
    )
    _, template_version = published_entity_mapping(db, organization_id, actor)
    schema = discovered_schema(db, organization_id, dataset_id, version_id, "cm01-wrong-version")
    other_version_id = second_dataset_version(
        db, organization_id, dataset_id, actor, "cm01-wrong-version-2"
    )
    with pytest.raises(CanonicalMappingServiceError) as exc:
        mapping_execution_service.execute(
            db,
            organization_id,
            _request(
                other_version_id,
                template_version.id,
                schema.id,
                "cm01-wrong-version-run",
                raw_reference_id,
            ),
            actor,
        )
    assert (exc.value.code, exc.value.status) == ("SOURCE_SCHEMA_DATASET_VERSION_MISMATCH", 409)


def test_changed_source_schema_is_rejected(db: Session) -> None:
    organization_id, actor, dataset_id, version_id, _, raw_reference_id = foundation(
        db, "cm01-changed"
    )
    _, template_version = published_entity_mapping(db, organization_id, actor)
    schema = discovered_schema(db, organization_id, dataset_id, version_id, "cm01-changed")
    schema.status = "changed"
    db.commit()
    with pytest.raises(CanonicalMappingServiceError) as exc:
        mapping_execution_service.execute(
            db,
            organization_id,
            _request(
                version_id, template_version.id, schema.id, "cm01-changed-run", raw_reference_id
            ),
            actor,
        )
    assert (exc.value.code, exc.value.status) == ("SOURCE_SCHEMA_NOT_USABLE", 409)


def test_incompatible_source_schema_is_rejected(db: Session) -> None:
    organization_id, actor, dataset_id, version_id, _, raw_reference_id = foundation(
        db, "cm01-incompatible"
    )
    _, template_version = published_entity_mapping(db, organization_id, actor)
    schema = discovered_schema(db, organization_id, dataset_id, version_id, "cm01-incompatible")
    schema.status = "incompatible"
    db.commit()
    with pytest.raises(CanonicalMappingServiceError) as exc:
        mapping_execution_service.execute(
            db,
            organization_id,
            _request(
                version_id,
                template_version.id,
                schema.id,
                "cm01-incompatible-run",
                raw_reference_id,
            ),
            actor,
        )
    assert (exc.value.code, exc.value.status) == ("SOURCE_SCHEMA_NOT_USABLE", 409)


def test_usable_schema_status_is_accepted(db: Session) -> None:
    organization_id, actor, dataset_id, version_id, _, raw_reference_id = foundation(
        db, "cm01-stable"
    )
    _, template_version = published_entity_mapping(db, organization_id, actor)
    schema = discovered_schema(db, organization_id, dataset_id, version_id, "cm01-stable")
    schema.status = "stable"
    db.commit()
    run = mapping_execution_service.execute(
        db,
        organization_id,
        _request(version_id, template_version.id, schema.id, "cm01-stable-run", raw_reference_id),
        actor,
    )
    assert run.source_schema_id == schema.id


def test_multiple_schemas_require_explicit_selection(db: Session) -> None:
    organization_id, actor, dataset_id, version_id, _, raw_reference_id = foundation(
        db, "cm01-multi"
    )
    _, template_version = published_entity_mapping(db, organization_id, actor)
    schema_a = discovered_schema(db, organization_id, dataset_id, version_id, "cm01-multi-a")
    schema_b = discovered_schema(db, organization_id, dataset_id, version_id, "cm01-multi-b")
    assert schema_a.id != schema_b.id
    assert schema_a.dataset_version_id == schema_b.dataset_version_id
    run = mapping_execution_service.execute(
        db,
        organization_id,
        _request(version_id, template_version.id, schema_a.id, "cm01-multi-run", raw_reference_id),
        actor,
    )
    assert run.source_schema_id == schema_a.id
    assert run.schema_fingerprint_snapshot == schema_a.schema_fingerprint
    assert run.schema_fingerprint_snapshot != schema_b.schema_fingerprint


def test_run_remains_bound_to_original_schema_after_newer_discovery(db: Session) -> None:
    organization_id, actor, dataset_id, version_id, _, raw_reference_id = foundation(
        db, "cm01-temporal"
    )
    _, template_version = published_entity_mapping(db, organization_id, actor)
    schema_a = discovered_schema(db, organization_id, dataset_id, version_id, "cm01-temporal-a")
    run = mapping_execution_service.execute(
        db,
        organization_id,
        _request(
            version_id, template_version.id, schema_a.id, "cm01-temporal-run", raw_reference_id
        ),
        actor,
    )
    schema_b = discovered_schema(db, organization_id, dataset_id, version_id, "cm01-temporal-b")
    refreshed = db.get(MappingRun, run.id)
    assert refreshed is not None
    assert refreshed.source_schema_id == schema_a.id
    assert refreshed.schema_fingerprint_snapshot == schema_a.schema_fingerprint
    assert refreshed.source_schema_id != schema_b.id


def test_same_template_against_two_schemas_remains_distinguishable(db: Session) -> None:
    organization_id, actor, dataset_id, version_id, _, raw_reference_id = foundation(
        db, "cm01-distinct"
    )
    _, template_version = published_entity_mapping(db, organization_id, actor)
    schema_a = discovered_schema(db, organization_id, dataset_id, version_id, "cm01-distinct-a")
    schema_b = discovered_schema(db, organization_id, dataset_id, version_id, "cm01-distinct-b")
    run_a = mapping_execution_service.execute(
        db,
        organization_id,
        _request(
            version_id, template_version.id, schema_a.id, "cm01-distinct-run-a", raw_reference_id
        ),
        actor,
    )
    run_b = mapping_execution_service.execute(
        db,
        organization_id,
        _request(
            version_id, template_version.id, schema_b.id, "cm01-distinct-run-b", raw_reference_id
        ),
        actor,
    )
    assert run_a.source_schema_id != run_b.source_schema_id
    assert run_a.schema_fingerprint_snapshot != run_b.schema_fingerprint_snapshot


def test_idempotency_replay_and_schema_conflict(db: Session) -> None:
    organization_id, actor, dataset_id, version_id, _, raw_reference_id = foundation(
        db, "cm01-idempotency"
    )
    _, template_version = published_entity_mapping(db, organization_id, actor)
    schema_a = discovered_schema(db, organization_id, dataset_id, version_id, "cm01-idem-a")
    schema_b = discovered_schema(db, organization_id, dataset_id, version_id, "cm01-idem-b")
    request = _request(
        version_id, template_version.id, schema_a.id, "cm01-idem-key", raw_reference_id
    )
    first = mapping_execution_service.execute(db, organization_id, request, actor)
    replay = mapping_execution_service.execute(db, organization_id, request, actor)
    assert replay.id == first.id
    assert replay.source_schema_id == schema_a.id

    conflicting = request.model_copy(update={"source_schema_id": schema_b.id})
    with pytest.raises(CanonicalMappingServiceError) as exc:
        mapping_execution_service.execute(db, organization_id, conflicting, actor)
    assert (exc.value.code, exc.value.status) == ("IDEMPOTENCY_CONFLICT", 409)


def test_historical_null_provenance_row_remains_readable_and_is_not_backfilled(
    db: Session,
) -> None:
    organization_id, actor, _, version_id, _, _ = foundation(db, "cm01-historical")
    _, template_version = published_entity_mapping(db, organization_id, actor)
    historical = MappingRun(
        organization_id=organization_id,
        dataset_version_id=version_id,
        template_version_id=template_version.id,
        source_schema_id=None,
        schema_fingerprint_snapshot=None,
        status="completed",
        idempotency_key="cm01-historical-run",
        request_fingerprint="a" * 64,
        input_count=0,
        mapped_count=0,
        exception_count=0,
        rejected_count=0,
        created_by_user_id=actor,
    )
    db.add(historical)
    db.commit()
    db.refresh(historical)
    assert historical.source_schema_id is None
    assert historical.schema_fingerprint_snapshot is None

    reread = db.get(MappingRun, historical.id)
    assert reread is not None
    assert reread.source_schema_id is None
    assert reread.schema_fingerprint_snapshot is None


def test_execute_mapping_never_infers_or_selects_a_schema_automatically() -> None:
    source = inspect.getsource(mapping_execution_service.execute)
    assert "for_dataset_version" not in source
    assert "discovered_at" not in source
    assert "order_by" not in source


def test_no_field_level_source_field_enforcement_is_added(db: Session) -> None:
    organization_id, actor, dataset_id, version_id, _, raw_reference_id = foundation(
        db, "cm01-no-field-check"
    )
    _, template_version = published_entity_mapping(db, organization_id, actor)
    schema = discovered_schema(db, organization_id, dataset_id, version_id, "cm01-no-field-check")
    assert (
        db.scalar(
            select(func.count())
            .select_from(SourceField)
            .where(SourceField.source_schema_id == schema.id)
        )
        == 0
    )
    run = mapping_execution_service.execute(
        db,
        organization_id,
        _request(
            version_id,
            template_version.id,
            schema.id,
            "cm01-no-field-check-run",
            raw_reference_id,
        ),
        actor,
    )
    assert run.status == "completed"
    assert run.mapped_count == 1


def test_trust_and_operational_memory_are_unaffected(db: Session) -> None:
    organization_id, actor, dataset_id, version_id, _, raw_reference_id = foundation(
        db, "cm01-trust"
    )
    _, template_version = published_entity_mapping(db, organization_id, actor)
    schema = discovered_schema(db, organization_id, dataset_id, version_id, "cm01-trust")
    trust_before = db.scalar(
        select(func.count())
        .select_from(TrustAssessment)
        .where(TrustAssessment.organization_id == organization_id)
    )
    memory_before = db.scalar(
        select(func.count())
        .select_from(OperationalMemoryItem)
        .where(OperationalMemoryItem.organization_id == organization_id)
    )
    mapping_execution_service.execute(
        db,
        organization_id,
        _request(version_id, template_version.id, schema.id, "cm01-trust-run", raw_reference_id),
        actor,
    )
    trust_after = db.scalar(
        select(func.count())
        .select_from(TrustAssessment)
        .where(TrustAssessment.organization_id == organization_id)
    )
    memory_after = db.scalar(
        select(func.count())
        .select_from(OperationalMemoryItem)
        .where(OperationalMemoryItem.organization_id == organization_id)
    )
    assert trust_after == trust_before
    assert memory_after == memory_before


def test_no_ai_or_vector_dependency_introduced() -> None:
    source = (
        Path("app/services/canonical_mapping_service.py").read_text(encoding="utf-8").casefold()
    )
    prohibited = ("openai", "anthropic", "gemini", "pgvector", "embedding", "vector database")
    assert not any(value in source for value in prohibited)
