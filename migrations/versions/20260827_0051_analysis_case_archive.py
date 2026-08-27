"""P3.xxC.1E: soft-archive columns for AnalysisCase.

Two nullable, additive columns only. Mirrors the existing Finding.archived_at
pattern -- archiving a case never deletes it or anything it produced
(artifacts, datasets, runs, findings, actions, recovery records); it only
sets archived_at/archived_by_user_id so the default list view can exclude
it while GET /{case_id} and every nested route keep working unchanged.

Revision ID: 20260827_0051
Revises: 20260826_0050
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260827_0051"
down_revision: str | None = "20260826_0050"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "analysis_cases", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("analysis_cases", sa.Column("archived_by_user_id", sa.Uuid(), nullable=True))


def downgrade() -> None:
    op.drop_column("analysis_cases", "archived_by_user_id")
    op.drop_column("analysis_cases", "archived_at")
