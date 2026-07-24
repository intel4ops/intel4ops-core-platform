"""Create the governed source systems registry.

Revision ID: 20260724_0003
Revises: 20260724_0002
Create Date: 2026-07-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260724_0003"
down_revision: str | None = "20260724_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

portable_json = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "source_systems",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("system_type", sa.String(length=50), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=True),
        sa.Column("integration_method", sa.String(length=50), nullable=False),
        sa.Column("environment", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("health_status", sa.String(length=30), nullable=False),
        sa.Column("base_url", sa.String(length=500), nullable=True),
        sa.Column("database_host_reference", sa.String(length=255), nullable=True),
        sa.Column("database_name_reference", sa.String(length=255), nullable=True),
        sa.Column("external_system_id", sa.String(length=255), nullable=True),
        sa.Column("owner_name", sa.String(length=200), nullable=True),
        sa.Column("owner_email", sa.String(length=320), nullable=True),
        sa.Column("data_classification", sa.String(length=30), nullable=False),
        sa.Column("timezone", sa.String(length=100), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("credential_reference", sa.String(length=500), nullable=True),
        sa.Column("last_connection_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_connection_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_connection_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_health_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.Column("configuration_metadata", portable_json, nullable=True),
        sa.Column("capabilities", portable_json, nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("failure_count >= 0", name="ck_source_systems_failure_count"),
        sa.CheckConstraint(
            "system_type IN ('erp', 'accounting', 'crm', 'cmms', 'eam', 'hrms', "
            "'payroll', 'inventory', 'procurement', 'point_of_sale', 'banking', "
            "'payment_processor', 'spreadsheet', 'flat_file', 'database', 'api', "
            "'scada', 'iot', 'gps_telematics', 'fleet_management', 'ticketing', "
            "'scheduling', 'document_repository', 'email', 'custom')",
            name="ck_source_systems_system_type",
        ),
        sa.CheckConstraint(
            "integration_method IN ('api', 'database', 'file_upload', 'file_drop', "
            "'sftp', 'webhook', 'message_queue', 'email_ingestion', 'manual', "
            "'device_stream', 'custom')",
            name="ck_source_systems_integration_method",
        ),
        sa.CheckConstraint(
            "environment IN ('production', 'staging', 'development', 'test', 'sandbox')",
            name="ck_source_systems_environment",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'configured', 'validating', 'active', 'paused', "
            "'failed', 'decommissioned')",
            name="ck_source_systems_status",
        ),
        sa.CheckConstraint(
            "health_status IN ('unknown', 'healthy', 'degraded', 'unhealthy', 'unavailable')",
            name="ck_source_systems_health_status",
        ),
        sa.CheckConstraint(
            "data_classification IN ('public', 'internal', 'confidential', 'restricted')",
            name="ck_source_systems_data_classification",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_source_systems_organization_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "code", name="uq_source_systems_organization_code"),
    )
    for column in (
        "organization_id",
        "system_type",
        "status",
        "health_status",
        "provider",
        "is_active",
    ):
        op.create_index(f"ix_source_systems_{column}", "source_systems", [column])


def downgrade() -> None:
    for column in (
        "is_active",
        "provider",
        "health_status",
        "status",
        "system_type",
        "organization_id",
    ):
        op.drop_index(f"ix_source_systems_{column}", table_name="source_systems")
    op.drop_table("source_systems")
