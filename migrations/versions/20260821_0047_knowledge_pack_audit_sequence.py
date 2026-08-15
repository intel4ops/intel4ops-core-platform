"""Add deterministic Knowledge Pack audit event ordering.

occurred_at alone cannot guarantee read-order for audit events recorded
within the same timestamp resolution window (e.g. pack_created and
version_created, both written in the same request). Add an explicit,
service-assigned monotonic sequence column, backfill existing rows using
the best available ordering signal (occurred_at, id), then enforce it.

Revision ID: 20260821_0047
Revises: 20260820_0046
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

revision: str = "20260821_0047"
down_revision: str | None = "20260820_0046"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "knowledge_pack_audit_events"
_CHECK_NAME = "ck_pack_audit_sequence_positive"
_UNIQUE_NAME = "uq_pack_audit_org_pack_sequence"
_INDEX_NAME = "ix_pack_audit_org_pack_sequence"


def _backfill_sequence() -> None:
    if context.is_offline_mode():
        return
    connection = op.get_bind()
    metadata = sa.MetaData()
    audit = sa.Table(_TABLE, metadata, autoload_with=connection)
    rows = connection.execute(
        sa.select(
            audit.c.id, audit.c.organization_id, audit.c.knowledge_pack_id, audit.c.occurred_at
        ).order_by(
            audit.c.organization_id,
            audit.c.knowledge_pack_id,
            audit.c.occurred_at,
            audit.c.id,
        )
    ).fetchall()
    counters: dict[tuple[object, object], int] = {}
    for row in rows:
        key = (row.organization_id, row.knowledge_pack_id)
        counters[key] = counters.get(key, 0) + 1
        connection.execute(
            audit.update().where(audit.c.id == row.id).values(sequence=counters[key])
        )


def _validate_no_nulls_remain() -> None:
    if context.is_offline_mode():
        return
    connection = op.get_bind()
    metadata = sa.MetaData()
    audit = sa.Table(_TABLE, metadata, autoload_with=connection)
    remaining = connection.execute(
        sa.select(sa.func.count()).select_from(audit).where(audit.c.sequence.is_(None))
    ).scalar_one()
    if remaining:
        raise RuntimeError(
            f"{remaining} {_TABLE} row(s) still have a NULL sequence after backfill; "
            "refusing to enforce NOT NULL on an incompletely-backfilled column."
        )


def upgrade() -> None:
    op.add_column(_TABLE, sa.Column("sequence", sa.Integer(), nullable=True))
    _backfill_sequence()
    _validate_no_nulls_remain()
    with op.batch_alter_table(_TABLE) as batch:
        batch.alter_column("sequence", existing_type=sa.Integer(), nullable=False)
        batch.create_check_constraint(_CHECK_NAME, "sequence > 0")
        batch.create_unique_constraint(
            _UNIQUE_NAME, ["organization_id", "knowledge_pack_id", "sequence"]
        )
    op.create_index(_INDEX_NAME, _TABLE, ["organization_id", "knowledge_pack_id", "sequence"])


def downgrade() -> None:
    op.drop_index(_INDEX_NAME, table_name=_TABLE)
    with op.batch_alter_table(_TABLE) as batch:
        batch.drop_constraint(_UNIQUE_NAME, type_="unique")
        batch.drop_constraint(_CHECK_NAME, type_="check")
        batch.drop_column("sequence")
