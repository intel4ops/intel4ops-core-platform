"""Enforce core tenant referential integrity.

Revision ID: 20260731_0025
Revises: 20260730_0024
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

revision: str = "20260731_0025"
down_revision: str | None = "20260730_0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PARENT_UNIQUES = (
    ("source_systems", "uq_source_systems_org_id"),
    ("datasets", "uq_datasets_org_id"),
    ("ingestion_batches", "uq_ingestion_batches_org_id"),
    ("dataset_versions", "uq_dataset_versions_org_id"),
    ("raw_storage_objects", "uq_raw_storage_objects_org_id"),
    ("processing_runs", "uq_processing_runs_org_id"),
    ("lineage_nodes", "uq_lineage_nodes_org_id"),
)

COMPOSITE_FOREIGN_KEYS = (
    (
        "ingestion_batches",
        "fk_ingestion_batches_org_source_system",
        "source_systems",
        "source_system_id",
    ),
    ("datasets", "fk_datasets_org_source_system", "source_systems", "source_system_id"),
    ("dataset_versions", "fk_dataset_versions_org_dataset", "datasets", "dataset_id"),
    (
        "dataset_versions",
        "fk_dataset_versions_org_ingestion_batch",
        "ingestion_batches",
        "ingestion_batch_id",
    ),
    (
        "raw_storage_objects",
        "fk_raw_storage_objects_org_source_system",
        "source_systems",
        "source_system_id",
    ),
    (
        "raw_storage_objects",
        "fk_raw_storage_objects_org_ingestion_batch",
        "ingestion_batches",
        "ingestion_batch_id",
    ),
    (
        "raw_storage_objects",
        "fk_raw_storage_objects_org_dataset_version",
        "dataset_versions",
        "dataset_version_id",
    ),
    (
        "raw_storage_objects",
        "fk_raw_storage_objects_org_supersedes",
        "raw_storage_objects",
        "supersedes_raw_object_id",
    ),
    (
        "raw_record_references",
        "fk_raw_record_references_org_raw_storage_object",
        "raw_storage_objects",
        "raw_storage_object_id",
    ),
    (
        "raw_record_references",
        "fk_raw_record_references_org_dataset_version",
        "dataset_versions",
        "dataset_version_id",
    ),
    (
        "processing_runs",
        "fk_processing_runs_org_ingestion_batch",
        "ingestion_batches",
        "ingestion_batch_id",
    ),
    (
        "processing_runs",
        "fk_processing_runs_org_dataset_version",
        "dataset_versions",
        "dataset_version_id",
    ),
    (
        "processing_runs",
        "fk_processing_runs_org_parent_run",
        "processing_runs",
        "parent_run_id",
    ),
    ("lineage_edges", "fk_lineage_edges_org_from_node", "lineage_nodes", "from_node_id"),
    ("lineage_edges", "fk_lineage_edges_org_to_node", "lineage_nodes", "to_node_id"),
    (
        "lineage_edges",
        "fk_lineage_edges_org_processing_run",
        "processing_runs",
        "processing_run_id",
    ),
    (
        "lineage_events",
        "fk_lineage_events_org_processing_run",
        "processing_runs",
        "processing_run_id",
    ),
)

COMPOSITE_INDEXES = (
    ("ingestion_batches", "ix_ingestion_batches_org_source_system_id", "source_system_id"),
    ("datasets", "ix_datasets_org_source_system_id", "source_system_id"),
    ("dataset_versions", "ix_dataset_versions_org_dataset_id", "dataset_id"),
    (
        "dataset_versions",
        "ix_dataset_versions_org_ingestion_batch_id",
        "ingestion_batch_id",
    ),
    (
        "raw_storage_objects",
        "ix_raw_storage_objects_org_source_system_id",
        "source_system_id",
    ),
    (
        "raw_storage_objects",
        "ix_raw_storage_objects_org_ingestion_batch_id",
        "ingestion_batch_id",
    ),
    (
        "raw_storage_objects",
        "ix_raw_storage_objects_org_dataset_version_id",
        "dataset_version_id",
    ),
    (
        "raw_storage_objects",
        "ix_raw_storage_objects_org_supersedes_raw_object_id",
        "supersedes_raw_object_id",
    ),
    (
        "raw_record_references",
        "ix_raw_record_references_org_raw_storage_object_id",
        "raw_storage_object_id",
    ),
    (
        "raw_record_references",
        "ix_raw_record_references_org_dataset_version_id",
        "dataset_version_id",
    ),
    (
        "processing_runs",
        "ix_processing_runs_org_ingestion_batch_id",
        "ingestion_batch_id",
    ),
    (
        "processing_runs",
        "ix_processing_runs_org_dataset_version_id",
        "dataset_version_id",
    ),
    ("processing_runs", "ix_processing_runs_org_parent_run_id", "parent_run_id"),
    ("lineage_edges", "ix_lineage_edges_org_from_node_id", "from_node_id"),
    ("lineage_edges", "ix_lineage_edges_org_to_node_id", "to_node_id"),
    ("lineage_edges", "ix_lineage_edges_org_processing_run_id", "processing_run_id"),
    ("lineage_events", "ix_lineage_events_org_processing_run_id", "processing_run_id"),
)


def _assert_clean_tenant_references() -> None:
    bind = op.get_bind()
    for child, constraint_name, parent, parent_column in COMPOSITE_FOREIGN_KEYS:
        violations = bind.scalar(
            sa.text(
                f"""
                SELECT count(*)
                FROM {child} AS child
                LEFT JOIN {parent} AS parent ON parent.id = child.{parent_column}
                WHERE child.organization_id IS NULL
                   OR (
                       child.{parent_column} IS NOT NULL
                       AND (
                           parent.id IS NULL
                           OR parent.organization_id <> child.organization_id
                       )
                   )
                """
            )
        )
        if violations:
            raise RuntimeError(
                f"{constraint_name} precondition failed with {violations} violating rows"
            )

    for parent, constraint_name in PARENT_UNIQUES:
        duplicates = bind.scalar(
            sa.text(
                f"""
                SELECT count(*)
                FROM (
                    SELECT organization_id, id
                    FROM {parent}
                    GROUP BY organization_id, id
                    HAVING count(*) > 1
                ) AS duplicate_targets
                """
            )
        )
        if duplicates:
            raise RuntimeError(
                f"{constraint_name} precondition failed with {duplicates} duplicate targets"
            )


def upgrade() -> None:
    if not context.is_offline_mode():
        _assert_clean_tenant_references()

    for table_name, constraint_name in PARENT_UNIQUES:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.create_unique_constraint(
                constraint_name,
                ["organization_id", "id"],
            )

    for child, constraint_name, parent, parent_column in COMPOSITE_FOREIGN_KEYS:
        with op.batch_alter_table(child) as batch_op:
            batch_op.create_foreign_key(
                constraint_name,
                parent,
                ["organization_id", parent_column],
                ["organization_id", "id"],
                ondelete="RESTRICT",
            )

    for table_name, index_name, parent_column in COMPOSITE_INDEXES:
        op.create_index(
            index_name,
            table_name,
            ["organization_id", parent_column],
            unique=False,
        )


def downgrade() -> None:
    for table_name, index_name, _ in reversed(COMPOSITE_INDEXES):
        op.drop_index(index_name, table_name=table_name)

    for child, constraint_name, _, _ in reversed(COMPOSITE_FOREIGN_KEYS):
        with op.batch_alter_table(child) as batch_op:
            batch_op.drop_constraint(constraint_name, type_="foreignkey")

    for table_name, constraint_name in reversed(PARENT_UNIQUES):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_constraint(constraint_name, type_="unique")
