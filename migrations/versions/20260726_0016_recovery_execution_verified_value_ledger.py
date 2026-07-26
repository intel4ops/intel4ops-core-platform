"""recovery execution and verified value ledger

Revision ID: 20260726_0016
Revises: 20260726_0015
"""

from collections.abc import Sequence

from alembic import op

import app.models  # noqa: F401
from app.db.session import Base

revision: str = "20260726_0016"
down_revision: str | None = "20260726_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RECOVERY_LEDGER_TABLES = (
    "recovery_cases",
    "recovery_executions",
    "recovery_value_measurements",
    "recovery_evidence_links",
    "recovery_finance_verifications",
    "verified_value_ledger_entries",
    "recovery_audit_events",
)


def upgrade() -> None:
    bind = op.get_bind()
    for table_name in RECOVERY_LEDGER_TABLES:
        Base.metadata.tables[table_name].create(bind=bind, checkfirst=False)


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in reversed(RECOVERY_LEDGER_TABLES):
        Base.metadata.tables[table_name].drop(bind=bind, checkfirst=False)
