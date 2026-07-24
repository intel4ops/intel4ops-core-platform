"""Create ingestion batches, datasets, and dataset versions.

Revision ID: 20260724_0004
Revises: 20260724_0003
Create Date: 2026-07-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260724_0004"
down_revision: str | None = "20260724_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

portable_json = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "ingestion_batches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("source_system_id", sa.Uuid(), nullable=False),
        sa.Column("batch_number", sa.String(120), nullable=False),
        sa.Column("ingestion_method", sa.String(40), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("trigger_type", sa.String(30), nullable=False),
        sa.Column("submitted_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expected_dataset_count", sa.Integer(), nullable=True),
        sa.Column("actual_dataset_count", sa.Integer(), nullable=False),
        sa.Column("expected_record_count", sa.Integer(), nullable=True),
        sa.Column("actual_record_count", sa.Integer(), nullable=False),
        sa.Column("accepted_record_count", sa.Integer(), nullable=False),
        sa.Column("rejected_record_count", sa.Integer(), nullable=False),
        sa.Column("warning_count", sa.Integer(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.String(255), nullable=True),
        sa.Column("correlation_id", sa.String(255), nullable=True),
        sa.Column("external_batch_id", sa.String(255), nullable=True),
        sa.Column("idempotency_key", sa.String(255), nullable=True),
        sa.Column("storage_reference", sa.String(500), nullable=True),
        sa.Column("manifest_metadata", portable_json, nullable=True),
        sa.Column("failure_code", sa.String(100), nullable=True),
        sa.Column("failure_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "ingestion_method IN ('api', 'database_extract', 'file_upload', 'file_drop', "
            "'sftp', 'webhook', 'message_queue', 'email_ingestion', 'manual', "
            "'device_stream', 'simulated', 'custom')",
            name="ck_ingestion_batches_method",
        ),
        sa.CheckConstraint(
            "status IN ('received', 'queued', 'validating', 'processing', "
            "'partially_completed', 'completed', 'failed', 'cancelled', 'quarantined')",
            name="ck_ingestion_batches_status",
        ),
        sa.CheckConstraint(
            "trigger_type IN ('manual', 'scheduled', 'event', 'webhook', 'retry', "
            "'backfill', 'simulation', 'system')",
            name="ck_ingestion_batches_trigger",
        ),
        sa.CheckConstraint(
            "expected_dataset_count IS NULL OR expected_dataset_count >= 0",
            name="ck_ingestion_batches_expected_datasets",
        ),
        sa.CheckConstraint(
            "actual_dataset_count >= 0 AND actual_record_count >= 0 AND "
            "accepted_record_count >= 0 AND rejected_record_count >= 0 AND "
            "warning_count >= 0 AND error_count >= 0",
            name="ck_ingestion_batches_counts_nonnegative",
        ),
        sa.CheckConstraint(
            "expected_record_count IS NULL OR expected_record_count >= 0",
            name="ck_ingestion_batches_expected_records",
        ),
        sa.CheckConstraint(
            "accepted_record_count + rejected_record_count <= actual_record_count",
            name="ck_ingestion_batches_counts_reconciled",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_ingestion_batches_organization_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_system_id"],
            ["source_systems.id"],
            name="fk_ingestion_batches_source_system_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "batch_number",
            name="uq_ingestion_batches_organization_batch",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_ingestion_batches_organization_idempotency",
        ),
    )
    for column in (
        "organization_id",
        "source_system_id",
        "status",
        "ingestion_method",
        "trigger_type",
        "received_at",
        "correlation_id",
        "external_batch_id",
    ):
        op.create_index(f"ix_ingestion_batches_{column}", "ingestion_batches", [column])

    op.create_table(
        "datasets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("source_system_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("domain", sa.String(100), nullable=False),
        sa.Column("dataset_type", sa.String(40), nullable=False),
        sa.Column("sensitivity", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("schema_status", sa.String(30), nullable=False),
        sa.Column("primary_time_field", sa.String(150), nullable=True),
        sa.Column("primary_business_key", sa.String(150), nullable=True),
        sa.Column("source_object_name", sa.String(255), nullable=True),
        sa.Column("source_schema_name", sa.String(255), nullable=True),
        sa.Column("source_table_name", sa.String(255), nullable=True),
        sa.Column("file_pattern", sa.String(255), nullable=True),
        sa.Column("default_timezone", sa.String(100), nullable=True),
        sa.Column("default_currency", sa.String(3), nullable=True),
        sa.Column("retention_days", sa.Integer(), nullable=True),
        sa.Column("metadata_json", portable_json, nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "dataset_type IN ('transactional', 'master_data', 'reference_data', "
            "'event_stream', 'snapshot', 'time_series', 'document', 'geospatial', "
            "'unstructured', 'semi_structured', 'custom')",
            name="ck_datasets_type",
        ),
        sa.CheckConstraint(
            "sensitivity IN ('public', 'internal', 'confidential', 'restricted')",
            name="ck_datasets_sensitivity",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'paused', 'deprecated', 'decommissioned')",
            name="ck_datasets_status",
        ),
        sa.CheckConstraint(
            "schema_status IN ('unknown', 'discovered', 'stable', 'changed', "
            "'incompatible', 'approved')",
            name="ck_datasets_schema_status",
        ),
        sa.CheckConstraint(
            "retention_days IS NULL OR retention_days > 0",
            name="ck_datasets_retention_days",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_datasets_organization_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_system_id"],
            ["source_systems.id"],
            name="fk_datasets_source_system_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "code", name="uq_datasets_organization_code"),
    )
    for column in (
        "organization_id",
        "source_system_id",
        "domain",
        "dataset_type",
        "status",
        "sensitivity",
        "schema_status",
    ):
        op.create_index(f"ix_datasets_{column}", "datasets", [column])

    op.create_table(
        "dataset_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("ingestion_batch_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("source_file_name", sa.String(255), nullable=True),
        sa.Column("source_file_extension", sa.String(30), nullable=True),
        sa.Column("source_file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("source_file_checksum", sa.String(255), nullable=True),
        sa.Column("media_type", sa.String(150), nullable=True),
        sa.Column("encoding", sa.String(50), nullable=True),
        sa.Column("delimiter", sa.String(10), nullable=True),
        sa.Column("sheet_name", sa.String(150), nullable=True),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("accepted_record_count", sa.Integer(), nullable=False),
        sa.Column("rejected_record_count", sa.Integer(), nullable=False),
        sa.Column("column_count", sa.Integer(), nullable=True),
        sa.Column("storage_reference", sa.String(500), nullable=True),
        sa.Column("raw_schema_reference", sa.String(500), nullable=True),
        sa.Column("source_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("schema_fingerprint", sa.String(255), nullable=True),
        sa.Column("metadata_json", portable_json, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version_number > 0", name="ck_dataset_versions_version_positive"),
        sa.CheckConstraint(
            "status IN ('received', 'validating', 'accepted', 'partially_accepted', "
            "'rejected', 'quarantined', 'processed', 'failed')",
            name="ck_dataset_versions_status",
        ),
        sa.CheckConstraint(
            "record_count >= 0 AND accepted_record_count >= 0 AND rejected_record_count >= 0",
            name="ck_dataset_versions_counts_nonnegative",
        ),
        sa.CheckConstraint(
            "accepted_record_count + rejected_record_count <= record_count",
            name="ck_dataset_versions_counts_reconciled",
        ),
        sa.CheckConstraint(
            "source_file_size_bytes IS NULL OR source_file_size_bytes >= 0",
            name="ck_dataset_versions_file_size",
        ),
        sa.CheckConstraint(
            "column_count IS NULL OR column_count >= 0",
            name="ck_dataset_versions_column_count",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_dataset_versions_organization_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.id"],
            name="fk_dataset_versions_dataset_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ingestion_batch_id"],
            ["ingestion_batches.id"],
            name="fk_dataset_versions_ingestion_batch_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "dataset_id",
            "version_number",
            name="uq_dataset_versions_dataset_version",
        ),
        sa.UniqueConstraint(
            "ingestion_batch_id",
            "dataset_id",
            name="uq_dataset_versions_batch_dataset",
        ),
    )
    for column in (
        "organization_id",
        "dataset_id",
        "ingestion_batch_id",
        "status",
        "received_at",
    ):
        op.create_index(f"ix_dataset_versions_{column}", "dataset_versions", [column])


def downgrade() -> None:
    for column in (
        "received_at",
        "status",
        "ingestion_batch_id",
        "dataset_id",
        "organization_id",
    ):
        op.drop_index(f"ix_dataset_versions_{column}", table_name="dataset_versions")
    op.drop_table("dataset_versions")
    for column in (
        "schema_status",
        "sensitivity",
        "status",
        "dataset_type",
        "domain",
        "source_system_id",
        "organization_id",
    ):
        op.drop_index(f"ix_datasets_{column}", table_name="datasets")
    op.drop_table("datasets")
    for column in (
        "external_batch_id",
        "correlation_id",
        "received_at",
        "trigger_type",
        "ingestion_method",
        "status",
        "source_system_id",
        "organization_id",
    ):
        op.drop_index(f"ix_ingestion_batches_{column}", table_name="ingestion_batches")
    op.drop_table("ingestion_batches")
