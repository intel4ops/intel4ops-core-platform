from datetime import UTC, datetime
from importlib import import_module
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy import (
    ForeignKeyConstraint,
    Index,
    UniqueConstraint,
    create_engine,
    delete,
    select,
    text,
    update,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, configure_mappers
from test_raw_lineage_service import foundation

import app.models  # noqa: F401
from app.db.session import Base
from app.models.ingestion import Dataset, DatasetVersion, IngestionBatch
from app.models.raw_lineage import (
    LineageEdge,
    LineageEvent,
    LineageNode,
    ProcessingRun,
    RawRecordReference,
    RawStorageObject,
)

PARENT_CONSTRAINTS = {
    "source_systems": "uq_source_systems_org_id",
    "datasets": "uq_datasets_org_id",
    "ingestion_batches": "uq_ingestion_batches_org_id",
    "dataset_versions": "uq_dataset_versions_org_id",
    "raw_storage_objects": "uq_raw_storage_objects_org_id",
    "processing_runs": "uq_processing_runs_org_id",
    "lineage_nodes": "uq_lineage_nodes_org_id",
}

TENANT_FOREIGN_KEYS = {
    "fk_ingestion_batches_org_source_system",
    "fk_datasets_org_source_system",
    "fk_dataset_versions_org_dataset",
    "fk_dataset_versions_org_ingestion_batch",
    "fk_raw_storage_objects_org_source_system",
    "fk_raw_storage_objects_org_ingestion_batch",
    "fk_raw_storage_objects_org_dataset_version",
    "fk_raw_storage_objects_org_supersedes",
    "fk_raw_record_references_org_raw_storage_object",
    "fk_raw_record_references_org_dataset_version",
    "fk_processing_runs_org_ingestion_batch",
    "fk_processing_runs_org_dataset_version",
    "fk_processing_runs_org_parent_run",
    "fk_lineage_edges_org_from_node",
    "fk_lineage_edges_org_to_node",
    "fk_lineage_edges_org_processing_run",
    "fk_lineage_events_org_processing_run",
}

TENANT_INDEXES = {
    "ix_ingestion_batches_org_source_system_id",
    "ix_datasets_org_source_system_id",
    "ix_dataset_versions_org_dataset_id",
    "ix_dataset_versions_org_ingestion_batch_id",
    "ix_raw_storage_objects_org_source_system_id",
    "ix_raw_storage_objects_org_ingestion_batch_id",
    "ix_raw_storage_objects_org_dataset_version_id",
    "ix_raw_storage_objects_org_supersedes_raw_object_id",
    "ix_raw_record_references_org_raw_storage_object_id",
    "ix_raw_record_references_org_dataset_version_id",
    "ix_processing_runs_org_ingestion_batch_id",
    "ix_processing_runs_org_dataset_version_id",
    "ix_processing_runs_org_parent_run_id",
    "ix_lineage_edges_org_from_node_id",
    "ix_lineage_edges_org_to_node_id",
    "ix_lineage_edges_org_processing_run_id",
    "ix_lineage_events_org_processing_run_id",
}


def test_model_metadata_and_mappers_define_exact_tenant_contract() -> None:
    configure_mappers()
    for table_name, constraint_name in PARENT_CONSTRAINTS.items():
        table = Base.metadata.tables[table_name]
        matches = [
            constraint
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint) and constraint.name == constraint_name
        ]
        assert len(matches) == 1
        assert [column.name for column in matches[0].columns] == ["organization_id", "id"]

    foreign_keys = {
        constraint.name
        for table in Base.metadata.tables.values()
        for constraint in table.constraints
        if isinstance(constraint, ForeignKeyConstraint) and constraint.name in TENANT_FOREIGN_KEYS
    }
    indexes = {
        index.name
        for table in Base.metadata.tables.values()
        for index in table.indexes
        if isinstance(index, Index) and index.name in TENANT_INDEXES
    }
    assert foreign_keys == TENANT_FOREIGN_KEYS
    assert indexes == TENANT_INDEXES


def test_precondition_diagnostic_detects_synthetic_tenant_mismatch() -> None:
    migration = import_module(
        "migrations.versions.20260731_0025_ti_a_core_tenant_referential_integrity"
    )
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE source_systems (id TEXT PRIMARY KEY, organization_id TEXT NOT NULL)")
        )
        connection.execute(
            text(
                "CREATE TABLE ingestion_batches "
                "(id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, "
                "source_system_id TEXT NOT NULL)"
            )
        )
        connection.execute(
            text("INSERT INTO source_systems (id, organization_id) VALUES ('source-1', 'tenant-a')")
        )
        connection.execute(
            text(
                "INSERT INTO ingestion_batches "
                "(id, organization_id, source_system_id) "
                "VALUES ('batch-1', 'tenant-b', 'source-1')"
            )
        )
        with (
            patch.object(
                migration,
                "COMPOSITE_FOREIGN_KEYS",
                (
                    (
                        "ingestion_batches",
                        "fk_ingestion_batches_org_source_system",
                        "source_systems",
                        "source_system_id",
                    ),
                ),
            ),
            patch.object(
                migration,
                "PARENT_UNIQUES",
                (("source_systems", "uq_source_systems_org_id"),),
            ),
            patch.object(migration.op, "get_bind", return_value=connection),
            pytest.raises(RuntimeError, match="1 violating rows"),
        ):
            migration._assert_clean_tenant_references()


def _raw_object(
    organization_id: UUID,
    source_id: UUID,
    batch_id: UUID,
    version_id: UUID,
    actor: UUID,
    suffix: str,
    *,
    supersedes: UUID | None = None,
) -> RawStorageObject:
    return RawStorageObject(
        organization_id=organization_id,
        source_system_id=source_id,
        ingestion_batch_id=batch_id,
        dataset_version_id=version_id,
        object_number=f"raw-{suffix}",
        object_type="file",
        storage_provider="s3",
        storage_reference=f"s3://opaque/{suffix}",
        content_checksum_algorithm="sha256",
        content_checksum=suffix[0] * 64,
        size_bytes=1,
        status="registered",
        integrity_status="unknown",
        retention_class="standard",
        received_at=datetime.now(UTC),
        supersedes_raw_object_id=supersedes,
        created_by_user_id=actor,
    )


def _tenant_rows(db: Session, slug: str) -> dict[str, UUID]:
    organization_id, source_id, batch_id, dataset_id, version_id = foundation(db, slug)
    actor = uuid4()
    raw_parent = _raw_object(
        organization_id, source_id, batch_id, version_id, actor, f"{slug}-parent"
    )
    db.add(raw_parent)
    db.flush()
    raw_child = _raw_object(
        organization_id,
        source_id,
        batch_id,
        version_id,
        actor,
        f"{slug}-child",
        supersedes=raw_parent.id,
    )
    db.add(raw_child)
    db.flush()
    record = RawRecordReference(
        organization_id=organization_id,
        raw_storage_object_id=raw_child.id,
        dataset_version_id=version_id,
        record_sequence=1,
    )
    parent_run = ProcessingRun(
        organization_id=organization_id,
        ingestion_batch_id=batch_id,
        dataset_version_id=version_id,
        run_type="integrity_verification",
        executor_type="worker",
        created_by_user_id=actor,
    )
    db.add_all([record, parent_run])
    db.flush()
    child_run = ProcessingRun(
        organization_id=organization_id,
        ingestion_batch_id=batch_id,
        dataset_version_id=version_id,
        run_type="integrity_verification",
        executor_type="worker",
        parent_run_id=parent_run.id,
        created_by_user_id=actor,
    )
    from_node = LineageNode(
        organization_id=organization_id,
        node_type="source_system",
        entity_id=source_id,
    )
    to_node = LineageNode(
        organization_id=organization_id,
        node_type="ingestion_batch",
        entity_id=batch_id,
    )
    db.add_all([child_run, from_node, to_node])
    db.flush()
    edge = LineageEdge(
        organization_id=organization_id,
        from_node_id=from_node.id,
        to_node_id=to_node.id,
        relationship_type="derived_from",
        processing_run_id=child_run.id,
        processing_run_key=str(child_run.id),
        created_by_user_id=actor,
    )
    event = LineageEvent(
        organization_id=organization_id,
        event_type="registered",
        entity_type="processing_run",
        entity_id=child_run.id,
        processing_run_id=child_run.id,
        actor_type="system",
    )
    db.add_all([edge, event])
    db.commit()
    return {
        "organization": organization_id,
        "source": source_id,
        "batch": batch_id,
        "dataset": dataset_id,
        "version": version_id,
        "raw_parent": raw_parent.id,
        "raw_child": raw_child.id,
        "record": record.id,
        "parent_run": parent_run.id,
        "child_run": child_run.id,
        "from_node": from_node.id,
        "to_node": to_node.id,
        "edge": edge.id,
        "event": event.id,
    }


def test_sqlite_rejects_cross_tenant_parent_updates_without_partial_rows(
    db: Session,
) -> None:
    first = _tenant_rows(db, f"ti-a-first-{uuid4().hex[:8]}")
    second = _tenant_rows(db, f"ti-a-second-{uuid4().hex[:8]}")
    cases = (
        (IngestionBatch, first["batch"], "source_system_id", second["source"]),
        (Dataset, first["dataset"], "source_system_id", second["source"]),
        (DatasetVersion, first["version"], "dataset_id", second["dataset"]),
        (DatasetVersion, first["version"], "ingestion_batch_id", second["batch"]),
        (RawStorageObject, first["raw_child"], "source_system_id", second["source"]),
        (RawStorageObject, first["raw_child"], "ingestion_batch_id", second["batch"]),
        (RawStorageObject, first["raw_child"], "dataset_version_id", second["version"]),
        (
            RawStorageObject,
            first["raw_child"],
            "supersedes_raw_object_id",
            second["raw_parent"],
        ),
        (
            RawRecordReference,
            first["record"],
            "raw_storage_object_id",
            second["raw_child"],
        ),
        (RawRecordReference, first["record"], "dataset_version_id", second["version"]),
        (ProcessingRun, first["child_run"], "ingestion_batch_id", second["batch"]),
        (ProcessingRun, first["child_run"], "dataset_version_id", second["version"]),
        (ProcessingRun, first["child_run"], "parent_run_id", second["parent_run"]),
        (LineageEdge, first["edge"], "from_node_id", second["from_node"]),
        (LineageEdge, first["edge"], "to_node_id", second["to_node"]),
        (LineageEdge, first["edge"], "processing_run_id", second["child_run"]),
        (LineageEvent, first["event"], "processing_run_id", second["child_run"]),
    )
    for model, row_id, column_name, wrong_parent_id in cases:
        with pytest.raises(IntegrityError):
            db.execute(
                update(model).where(model.id == row_id).values({column_name: wrong_parent_id})
            )
            db.commit()
        db.rollback()
        assert db.scalar(select(model.id).where(model.id == row_id)) == row_id

    for cleanup_model in (
        LineageEvent,
        LineageEdge,
        RawRecordReference,
        LineageNode,
    ):
        db.execute(delete(cleanup_model))
    db.execute(
        delete(ProcessingRun).where(ProcessingRun.id.in_([first["child_run"], second["child_run"]]))
    )
    db.execute(delete(ProcessingRun))
    db.execute(
        delete(RawStorageObject).where(
            RawStorageObject.id.in_([first["raw_child"], second["raw_child"]])
        )
    )
    db.execute(delete(RawStorageObject))
    db.commit()


def test_nullable_tenant_parent_references_remain_valid(db: Session) -> None:
    rows = _tenant_rows(db, f"ti-a-nullable-{uuid4().hex[:8]}")
    db.execute(
        update(RawStorageObject)
        .where(RawStorageObject.id == rows["raw_child"])
        .values(supersedes_raw_object_id=None)
    )
    db.execute(
        update(ProcessingRun)
        .where(ProcessingRun.id == rows["child_run"])
        .values(
            ingestion_batch_id=None,
            dataset_version_id=None,
            parent_run_id=None,
            run_type="custom",
        )
    )
    db.execute(
        update(LineageEdge).where(LineageEdge.id == rows["edge"]).values(processing_run_id=None)
    )
    db.execute(
        update(LineageEvent).where(LineageEvent.id == rows["event"]).values(processing_run_id=None)
    )
    db.commit()
