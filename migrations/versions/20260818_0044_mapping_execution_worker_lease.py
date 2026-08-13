"""Add mapping execution worker ownership and dispatch indexes.

Revision ID: 20260818_0044
Revises: 20260817_0043
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260818_0044"
down_revision: str | None = "20260817_0043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("mapping_runs") as batch:
        batch.add_column(sa.Column("execution_lease_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("execution_worker_id", sa.String(length=200), nullable=True))
        batch.create_index("ix_mapping_run_dispatch_fifo", ["status", "created_at", "id"])
        batch.create_index("ix_mapping_run_stale_heartbeat", ["status", "heartbeat_at"])


def downgrade() -> None:
    with op.batch_alter_table("mapping_runs") as batch:
        batch.drop_index("ix_mapping_run_stale_heartbeat")
        batch.drop_index("ix_mapping_run_dispatch_fifo")
        batch.drop_column("execution_worker_id")
        batch.drop_column("execution_lease_id")
