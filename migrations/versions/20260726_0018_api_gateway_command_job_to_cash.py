"""API gateway, executive command, and Job-to-Cash vertical slice.

Revision ID: 20260726_0018
Revises: 20260726_0017
"""

from collections.abc import Sequence

from alembic import op

import app.models  # noqa: F401
from app.commercial.catalog import catalog_id
from app.db.session import Base

revision: str = "20260726_0018"
down_revision: str | None = "20260726_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "application_clients",
    "api_request_audit_events",
    "job_to_cash_runs",
    "job_to_cash_records",
)


def upgrade() -> None:
    bind = op.get_bind()
    for table_name in TABLES:
        Base.metadata.tables[table_name].create(bind=bind, checkfirst=False)
    op.bulk_insert(
        Base.metadata.tables["application_clients"],
        [
            {
                "id": catalog_id("application-client", code),
                "client_code": code,
                "name": name,
                "client_type": kind,
                "status": "active",
                "metadata_json": op.inline_literal("{}"),
            }
            for code, name, kind in (
                ("intel4ops-web", "Intel4Ops Web", "first_party"),
                ("partner-application", "Partner Application", "partner"),
                ("internal-simulator", "Internal Simulator", "internal"),
                ("administrative-tool", "Administrative Tool", "administrative"),
            )
        ],
        multiinsert=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in reversed(TABLES):
        Base.metadata.tables[table_name].drop(bind=bind, checkfirst=False)
