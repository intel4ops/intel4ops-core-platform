"""Add durable mapping-run execution, failure, input, and retry contract.

Revision ID: 20260817_0043
Revises: 20260816_0042
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260817_0043"
down_revision: str | None = "20260816_0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("mapping_runs") as batch:
        batch.add_column(sa.Column("failure_code", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("failure_message", sa.Text(), nullable=True))
        batch.add_column(sa.Column("failure_retryable", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("retry_of_run_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("root_run_id", sa.Uuid(), nullable=True))
        batch.add_column(
            sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1")
        )
        batch.add_column(sa.Column("execution_claimed_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("heartbeat_at", sa.DateTime(timezone=True)))
        batch.create_check_constraint("ck_mapping_run_attempt_number", "attempt_number >= 1")
        batch.create_foreign_key(
            "fk_mapping_run_retry_same_org",
            "mapping_runs",
            ["organization_id", "retry_of_run_id"],
            ["organization_id", "id"],
        )
        batch.create_foreign_key(
            "fk_mapping_run_root_same_org",
            "mapping_runs",
            ["organization_id", "root_run_id"],
            ["organization_id", "id"],
        )
        batch.create_unique_constraint(
            "uq_mapping_run_retry_child", ["organization_id", "retry_of_run_id"]
        )
        batch.create_index(
            "ix_mapping_run_retry_root", ["organization_id", "root_run_id", "attempt_number"]
        )

    op.execute("UPDATE mapping_runs SET root_run_id = id WHERE root_run_id IS NULL")

    op.create_table(
        "mapping_run_inputs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("mapping_run_id", sa.Uuid(), nullable=False),
        sa.Column("record_sequence", sa.Integer(), nullable=False),
        sa.Column("raw_record_reference_id", sa.Uuid(), nullable=False),
        sa.Column(
            "values_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("source_reported_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("record_sequence >= 0", name="ck_mapping_run_input_sequence"),
        sa.ForeignKeyConstraint(
            ["organization_id", "mapping_run_id"],
            ["mapping_runs.organization_id", "mapping_runs.id"],
            name="fk_mapping_run_inputs_org_run",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "raw_record_reference_id"],
            ["raw_record_references.organization_id", "raw_record_references.id"],
            name="fk_mapping_run_inputs_org_raw_record",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "mapping_run_id", "record_sequence", name="uq_mapping_run_input_sequence"
        ),
    )
    op.create_index(
        "ix_mapping_run_inputs_org_run",
        "mapping_run_inputs",
        ["organization_id", "mapping_run_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_mapping_run_inputs_org_run", table_name="mapping_run_inputs")
    op.drop_table("mapping_run_inputs")
    with op.batch_alter_table("mapping_runs") as batch:
        batch.drop_index("ix_mapping_run_retry_root")
        batch.drop_constraint("uq_mapping_run_retry_child", type_="unique")
        batch.drop_constraint("fk_mapping_run_root_same_org", type_="foreignkey")
        batch.drop_constraint("fk_mapping_run_retry_same_org", type_="foreignkey")
        batch.drop_constraint("ck_mapping_run_attempt_number", type_="check")
        batch.drop_column("heartbeat_at")
        batch.drop_column("execution_claimed_at")
        batch.drop_column("attempt_number")
        batch.drop_column("root_run_id")
        batch.drop_column("retry_of_run_id")
        batch.drop_column("failed_at")
        batch.drop_column("failure_retryable")
        batch.drop_column("failure_message")
        batch.drop_column("failure_code")
