"""predictive-to-action orchestration and closed-loop execution

Revision ID: 20260725_0014
Revises: 20260725_0013
"""

from collections.abc import Sequence

from alembic import op

import app.models  # noqa: F401
from app.db.session import Base

revision: str = "20260725_0014"
down_revision: str | None = "20260725_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACTION_TABLES = (
    "operational_actions",
    "action_plan_steps",
    "action_dependencies",
    "action_resource_requirements",
    "action_events",
    "action_evidence",
    "action_outcomes",
    "action_model_feedback",
)


def upgrade() -> None:
    bind = op.get_bind()
    for table_name in ACTION_TABLES:
        Base.metadata.tables[table_name].create(bind=bind, checkfirst=False)


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in reversed(ACTION_TABLES):
        Base.metadata.tables[table_name].drop(bind=bind, checkfirst=False)
