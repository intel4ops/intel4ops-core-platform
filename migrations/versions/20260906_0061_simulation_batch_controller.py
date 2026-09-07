"""AGENTIC-CONTROL-001 Phase H: Simulation Batch Controller state tracking

Revision ID: 20260906_0061
Revises: 20260906_0060
Create Date: 2026-09-06 12:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260906_0061"
down_revision: str | None = "20260906_0060"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BATCH_STATUSES = ("active", "paused_safety_gate", "owner_review_required", "complete")
_ITEM_STATES = (
    "available",
    "selected",
    "importing",
    "production_running",
    "terminal",
    "frozen",
    "validating",
    "scored",
    "miss_classification",
    "gap_clustering",
    "remediation_review",
    "retest",
    "regression",
    "graduated",
    "blocked",
)


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    op.create_table(
        "simulation_batches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("safety_gate_reason", sa.String(length=1000), nullable=True),
        sa.Column("decision_package_ref", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(f"status IN ({_quoted(_BATCH_STATUSES)})", name="ck_sim_batch_status"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_simulation_batch_org_created", "simulation_batches", ["organization_id", "created_at"]
    )

    op.create_table(
        "simulation_batch_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("simulation_id", sa.String(length=200), nullable=False),
        sa.Column("state", sa.String(length=30), nullable=False),
        sa.Column("analysis_case_id", sa.Uuid(), nullable=True),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("validation_simulation_id", sa.Uuid(), nullable=True),
        sa.Column("validation_run_id", sa.Uuid(), nullable=True),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("truth_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scored_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("true_positive_count", sa.Integer(), nullable=True),
        sa.Column("false_positive_count", sa.Integer(), nullable=True),
        sa.Column("false_negative_count", sa.Integer(), nullable=True),
        sa.Column("precision", sa.Float(), nullable=True),
        sa.Column("recall", sa.Float(), nullable=True),
        sa.Column("economic_capture_value", sa.Numeric(14, 2), nullable=True),
        sa.Column("economic_total_value", sa.Numeric(14, 2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("block_reason", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(f"state IN ({_quoted(_ITEM_STATES)})", name="ck_sim_batch_item_state"),
        sa.CheckConstraint(
            "truth_accessed_at IS NULL OR "
            "(frozen_at IS NOT NULL AND truth_accessed_at >= frozen_at)",
            name="ck_sim_batch_item_truth_isolation",
        ),
        sa.ForeignKeyConstraint(["batch_id"], ["simulation_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sim_batch_item_batch", "simulation_batch_items", ["batch_id"])
    op.create_index("ix_sim_batch_item_simulation", "simulation_batch_items", ["simulation_id"])
    op.create_index("ix_sim_batch_item_state", "simulation_batch_items", ["state"])


def downgrade() -> None:
    op.drop_index("ix_sim_batch_item_state", table_name="simulation_batch_items")
    op.drop_index("ix_sim_batch_item_simulation", table_name="simulation_batch_items")
    op.drop_index("ix_sim_batch_item_batch", table_name="simulation_batch_items")
    op.drop_table("simulation_batch_items")

    op.drop_index("ix_simulation_batch_org_created", table_name="simulation_batches")
    op.drop_table("simulation_batches")
