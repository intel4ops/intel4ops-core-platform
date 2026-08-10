"""Add field-mapping memory-origin lineage.

Revision ID: 20260815_0041
Revises: 20260814_0040
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260815_0041"
down_revision: str | None = "20260814_0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("field_mappings") as batch:
        batch.add_column(sa.Column("origin_memory_version_id", sa.Uuid(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("field_mappings") as batch:
        batch.drop_column("origin_memory_version_id")
