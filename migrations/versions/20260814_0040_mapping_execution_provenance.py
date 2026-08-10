"""Add mapping execution source-schema provenance.

Revision ID: 20260814_0040
Revises: 20260813_0039
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260814_0040"
down_revision: str | None = "20260813_0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("mapping_runs") as batch:
        batch.add_column(sa.Column("source_schema_id", sa.Uuid(), nullable=True))
        batch.add_column(
            sa.Column("schema_fingerprint_snapshot", sa.String(length=255), nullable=True)
        )
        batch.create_foreign_key(
            "fk_mapping_runs_org_source_schema",
            "source_schemas",
            ["organization_id", "source_schema_id"],
            ["organization_id", "id"],
            ondelete="RESTRICT",
        )
        batch.create_index(
            "ix_mapping_runs_org_source_schema",
            ["organization_id", "source_schema_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("mapping_runs") as batch:
        batch.drop_index("ix_mapping_runs_org_source_schema")
        batch.drop_constraint("fk_mapping_runs_org_source_schema", type_="foreignkey")
        batch.drop_column("schema_fingerprint_snapshot")
        batch.drop_column("source_schema_id")
