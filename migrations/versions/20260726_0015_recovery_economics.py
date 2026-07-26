"""exposure prioritization and recovery economics

Revision ID: 20260726_0015
Revises: 20260725_0014
"""

from collections.abc import Sequence

from alembic import op

import app.models  # noqa: F401
from app.db.session import Base

revision: str = "20260726_0015"
down_revision: str | None = "20260725_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ECONOMICS_TABLES = (
    "recovery_opportunities",
    "opportunity_findings",
    "opportunity_actions",
    "economic_scenarios",
    "economic_assumptions",
    "economic_calculations",
    "prioritization_assessments",
    "opportunity_overlap_groups",
    "opportunity_overlap_members",
    "opportunity_decisions",
    "economic_audit_events",
    "economic_baseline_versions",
)


def upgrade() -> None:
    bind = op.get_bind()
    for table_name in ECONOMICS_TABLES:
        Base.metadata.tables[table_name].create(bind=bind, checkfirst=False)


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in reversed(ECONOMICS_TABLES):
        Base.metadata.tables[table_name].drop(bind=bind, checkfirst=False)
