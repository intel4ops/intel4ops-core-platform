"""P3.xxD.1E.1 ground-truth package schema negotiation fix

Revision ID: 20260828_0054
Revises: 20260828_0053
Create Date: 2026-08-28 14:53:46.427404
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260828_0054"
down_revision: str | None = "20260828_0053"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "validation_ground_truths",
        sa.Column("source_schema_version", sa.String(length=50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("validation_ground_truths", "source_schema_version")
