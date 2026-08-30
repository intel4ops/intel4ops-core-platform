"""P3.xxE.2 adaptive field interpretation: AI provenance column

Revision ID: 20260831_0056
Revises: 20260830_0055
Create Date: 2026-08-31 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260831_0056"
down_revision: str | None = "20260830_0055"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "semantic_interpretation_decisions",
        sa.Column(
            "ai_provenance",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("semantic_interpretation_decisions", "ai_provenance")
