"""P3.xxC.1: additive Finding columns for Analysis Case governed findings.

Four nullable, additive columns only -- no change to any existing governed
Finding semantics, no backfill required. economic_status/currency_status
let Command distinguish a directly observed, currency-resolved value from
one still pending governed economics or currency resolution, without
overloading measured_value/exposure_value. entities_json/domains_json carry
the canonical entities and (for cross-domain findings) the constituent
domains a finding spans, queryable directly rather than parsed out of
evidence payloads.

Revision ID: 20260826_0050
Revises: 20260826_0049
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260826_0050"
down_revision: str | None = "20260826_0049"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
portable_json = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.add_column("findings", sa.Column("economic_status", sa.String(length=30), nullable=True))
    op.add_column("findings", sa.Column("currency_status", sa.String(length=20), nullable=True))
    op.add_column("findings", sa.Column("entities_json", portable_json, nullable=True))
    op.add_column("findings", sa.Column("domains_json", portable_json, nullable=True))


def downgrade() -> None:
    op.drop_column("findings", "domains_json")
    op.drop_column("findings", "entities_json")
    op.drop_column("findings", "currency_status")
    op.drop_column("findings", "economic_status")
