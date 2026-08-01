"""Enforce Forecasting and Forecast Actual tenant referential integrity.

Revision ID: 20260801_0028
Revises: 20260801_0027
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

revision: str = "20260801_0028"
down_revision: str | None = "20260801_0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PARENT_UNIQUES = (
    ("forecast_executions", "uq_forecast_executions_org_id"),
    ("forecast_points", "uq_forecast_points_org_id"),
)

COMPOSITE_FOREIGN_KEYS = (
    (
        "forecast_executions",
        "fk_forecast_executions_org_dataset",
        "datasets",
        "dataset_id",
        "RESTRICT",
    ),
    (
        "forecast_executions",
        "fk_forecast_executions_org_dataset_version",
        "dataset_versions",
        "dataset_version_id",
        "RESTRICT",
    ),
    (
        "forecast_executions",
        "fk_forecast_executions_org_ingestion_batch",
        "ingestion_batches",
        "ingestion_batch_id",
        "RESTRICT",
    ),
    (
        "forecast_executions",
        "fk_forecast_executions_org_source_system",
        "source_systems",
        "source_system_id",
        "RESTRICT",
    ),
    (
        "forecast_executions",
        "fk_forecast_executions_org_trust_assessment",
        "trust_assessments",
        "trust_assessment_id",
        "RESTRICT",
    ),
    (
        "forecast_executions",
        "fk_forecast_executions_org_readiness",
        "analytical_readiness_decisions",
        "readiness_assessment_id",
        "RESTRICT",
    ),
    (
        "forecast_points",
        "fk_forecast_points_org_execution",
        "forecast_executions",
        "forecast_execution_id",
        "CASCADE",
    ),
    (
        "forecast_scenarios",
        "fk_forecast_scenarios_org_execution",
        "forecast_executions",
        "forecast_execution_id",
        "CASCADE",
    ),
    (
        "forecast_revisions",
        "fk_forecast_revisions_org_prior_execution",
        "forecast_executions",
        "prior_forecast_execution_id",
        "RESTRICT",
    ),
    (
        "forecast_revisions",
        "fk_forecast_revisions_org_revised_execution",
        "forecast_executions",
        "revised_forecast_execution_id",
        "RESTRICT",
    ),
    (
        "forecast_actuals",
        "fk_forecast_actuals_org_forecast_point",
        "forecast_points",
        "forecast_point_id",
        "RESTRICT",
    ),
    ("forecast_actuals", "fk_forecast_actuals_org_dataset", "datasets", "dataset_id", "RESTRICT"),
    (
        "forecast_actuals",
        "fk_forecast_actuals_org_dataset_version",
        "dataset_versions",
        "dataset_version_id",
        "RESTRICT",
    ),
    (
        "forecast_actuals",
        "fk_forecast_actuals_org_ingestion_batch",
        "ingestion_batches",
        "ingestion_batch_id",
        "RESTRICT",
    ),
    (
        "forecast_actuals",
        "fk_forecast_actuals_org_source_system",
        "source_systems",
        "source_system_id",
        "RESTRICT",
    ),
    (
        "forecast_accuracy_results",
        "fk_forecast_accuracy_results_org_execution",
        "forecast_executions",
        "forecast_execution_id",
        "CASCADE",
    ),
    (
        "forecast_accuracy_results",
        "fk_forecast_accuracy_results_org_forecast_point",
        "forecast_points",
        "forecast_point_id",
        "CASCADE",
    ),
)

COMPOSITE_INDEXES = (
    ("forecast_executions", "ix_forecast_execution_org_dataset", "dataset_id"),
    ("forecast_executions", "ix_forecast_execution_org_dataset_version", "dataset_version_id"),
    ("forecast_executions", "ix_forecast_execution_org_ingestion_batch", "ingestion_batch_id"),
    ("forecast_executions", "ix_forecast_execution_org_source_system", "source_system_id"),
    ("forecast_executions", "ix_forecast_execution_org_trust_assessment", "trust_assessment_id"),
    ("forecast_executions", "ix_forecast_execution_org_readiness", "readiness_assessment_id"),
    ("forecast_points", "ix_forecast_point_org_execution", "forecast_execution_id"),
    ("forecast_scenarios", "ix_forecast_scenario_org_execution", "forecast_execution_id"),
    ("forecast_revisions", "ix_forecast_revision_org_revised", "revised_forecast_execution_id"),
    ("forecast_actuals", "ix_forecast_actual_org_dataset", "dataset_id"),
    ("forecast_actuals", "ix_forecast_actual_org_dataset_version", "dataset_version_id"),
    ("forecast_actuals", "ix_forecast_actual_org_ingestion_batch", "ingestion_batch_id"),
    ("forecast_actuals", "ix_forecast_actual_org_source_system", "source_system_id"),
    ("forecast_accuracy_results", "ix_forecast_accuracy_org_forecast_point", "forecast_point_id"),
)


def _assert_clean_tenant_references() -> None:
    bind = op.get_bind()
    for child, constraint_name, parent, parent_column, _ in COMPOSITE_FOREIGN_KEYS:
        violations = bind.scalar(
            sa.text(
                f"""
                SELECT count(*)
                FROM {child} AS child
                LEFT JOIN {parent} AS parent ON parent.id = child.{parent_column}
                WHERE child.organization_id IS NULL
                   OR (
                       child.{parent_column} IS NOT NULL
                       AND (
                           parent.id IS NULL
                           OR parent.organization_id <> child.organization_id
                       )
                   )
                """
            )
        )
        if violations:
            raise RuntimeError(
                f"{constraint_name} precondition failed with {violations} violating rows"
            )

    for parent, constraint_name in PARENT_UNIQUES:
        duplicates = bind.scalar(
            sa.text(
                f"""
                SELECT count(*)
                FROM (
                    SELECT organization_id, id
                    FROM {parent}
                    GROUP BY organization_id, id
                    HAVING count(*) > 1
                ) AS duplicate_targets
                """
            )
        )
        if duplicates:
            raise RuntimeError(
                f"{constraint_name} precondition failed with {duplicates} duplicate targets"
            )


def upgrade() -> None:
    if not context.is_offline_mode():
        _assert_clean_tenant_references()

    for table_name, constraint_name in PARENT_UNIQUES:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.create_unique_constraint(
                constraint_name,
                ["organization_id", "id"],
            )

    for child, constraint_name, parent, parent_column, ondelete in COMPOSITE_FOREIGN_KEYS:
        with op.batch_alter_table(child) as batch_op:
            batch_op.create_foreign_key(
                constraint_name,
                parent,
                ["organization_id", parent_column],
                ["organization_id", "id"],
                ondelete=ondelete,
            )

    for table_name, index_name, parent_column in COMPOSITE_INDEXES:
        op.create_index(
            index_name,
            table_name,
            ["organization_id", parent_column],
            unique=False,
        )


def downgrade() -> None:
    for table_name, index_name, _ in reversed(COMPOSITE_INDEXES):
        op.drop_index(index_name, table_name=table_name)

    for child, constraint_name, _, _, _ in reversed(COMPOSITE_FOREIGN_KEYS):
        with op.batch_alter_table(child) as batch_op:
            batch_op.drop_constraint(constraint_name, type_="foreignkey")

    for table_name, constraint_name in reversed(PARENT_UNIQUES):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_constraint(constraint_name, type_="unique")
