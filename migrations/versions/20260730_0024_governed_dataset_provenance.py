"""Add governed dataset provenance to analytical executions.

Revision ID: 20260730_0024
Revises: 20260728_0023
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

revision: str = "20260730_0024"
down_revision: str | None = "20260728_0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EXECUTION_TABLES = (
    "reliability_executions",
    "statistical_executions",
    "forecast_executions",
)
INDEX_PREFIXES = {
    "reliability_executions": "reliability_execution",
    "statistical_executions": "statistical_execution",
    "forecast_executions": "forecast_execution",
    "forecast_actuals": "forecast_actuals",
}
PROVENANCE_COLUMNS = (
    ("dataset_id", "datasets"),
    ("dataset_version_id", "dataset_versions"),
    ("ingestion_batch_id", "ingestion_batches"),
    ("source_system_id", "source_systems"),
)


def _add_provenance_columns(table_name: str) -> None:
    index_prefix = INDEX_PREFIXES[table_name]
    with op.batch_alter_table(table_name) as batch:
        for column_name, referenced_table in PROVENANCE_COLUMNS:
            batch.add_column(sa.Column(column_name, sa.Uuid(), nullable=True))
            batch.create_foreign_key(
                f"fk_{table_name}_{column_name}",
                referenced_table,
                [column_name],
                ["id"],
                ondelete="RESTRICT",
            )
        batch.create_index(f"ix_{index_prefix}_dataset_id", ["dataset_id"])
        batch.create_index(
            f"ix_{index_prefix}_dataset_version_id",
            ["dataset_version_id"],
        )


def _backfill_execution_table(table_name: str) -> None:
    if context.is_offline_mode():
        return
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            f"SELECT id, organization_id, dataset_reference, dataset_fingerprint "
            f"FROM {table_name} WHERE dataset_id IS NULL"
        )
    ).mappings()
    for row in rows:
        matches = list(
            bind.execute(
                sa.text(
                    "SELECT d.id AS dataset_id, dv.id AS dataset_version_id, "
                    "dv.ingestion_batch_id, ib.source_system_id "
                    "FROM datasets d "
                    "JOIN dataset_versions dv ON dv.dataset_id = d.id "
                    "AND dv.organization_id = d.organization_id "
                    "JOIN ingestion_batches ib ON ib.id = dv.ingestion_batch_id "
                    "AND ib.organization_id = d.organization_id "
                    "WHERE d.organization_id = :organization_id "
                    "AND d.code = :dataset_reference "
                    "AND d.source_system_id = ib.source_system_id "
                    "AND (dv.source_file_checksum = :dataset_fingerprint "
                    "OR dv.schema_fingerprint = :dataset_fingerprint)"
                ),
                {
                    "organization_id": row["organization_id"],
                    "dataset_reference": row["dataset_reference"],
                    "dataset_fingerprint": row["dataset_fingerprint"],
                },
            ).mappings()
        )
        if len(matches) != 1:
            continue
        match = matches[0]
        bind.execute(
            sa.text(
                f"UPDATE {table_name} SET dataset_id = :dataset_id, "
                "dataset_version_id = :dataset_version_id, "
                "ingestion_batch_id = :ingestion_batch_id, "
                "source_system_id = :source_system_id WHERE id = :id"
            ),
            {**dict(match), "id": row["id"]},
        )


def upgrade() -> None:
    for table_name in EXECUTION_TABLES:
        _add_provenance_columns(table_name)

    with op.batch_alter_table("forecast_actuals") as batch:
        for column_name, referenced_table in PROVENANCE_COLUMNS:
            batch.add_column(sa.Column(column_name, sa.Uuid(), nullable=True))
            batch.create_foreign_key(
                f"fk_forecast_actuals_{column_name}",
                referenced_table,
                [column_name],
                ["id"],
                ondelete="RESTRICT",
            )
        batch.create_index("ix_forecast_actuals_dataset_id", ["dataset_id"])
        batch.create_index(
            "ix_forecast_actuals_dataset_version_id",
            ["dataset_version_id"],
        )

    for table_name in EXECUTION_TABLES:
        _backfill_execution_table(table_name)


def downgrade() -> None:
    for table_name in (*EXECUTION_TABLES, "forecast_actuals"):
        index_prefix = INDEX_PREFIXES[table_name]
        with op.batch_alter_table(table_name) as batch:
            batch.drop_index(f"ix_{index_prefix}_dataset_version_id")
            batch.drop_index(f"ix_{index_prefix}_dataset_id")
            for column_name, _ in reversed(PROVENANCE_COLUMNS):
                batch.drop_constraint(
                    f"fk_{table_name}_{column_name}",
                    type_="foreignkey",
                )
                batch.drop_column(column_name)
