"""Enforce Reliability and Statistical tenant referential integrity.

Revision ID: 20260801_0027
Revises: 20260731_0026
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

revision: str = "20260801_0027"
down_revision: str | None = "20260731_0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PARENT_UNIQUES = (
    ("reliability_executions", "uq_reliability_executions_org_id"),
    ("statistical_executions", "uq_statistical_executions_org_id"),
    ("statistical_observations", "uq_statistical_observations_org_id"),
)

COMPOSITE_FOREIGN_KEYS = (
    (
        "reliability_executions",
        "fk_reliability_executions_org_dataset",
        "datasets",
        "dataset_id",
        "RESTRICT",
    ),
    (
        "reliability_executions",
        "fk_reliability_executions_org_dataset_version",
        "dataset_versions",
        "dataset_version_id",
        "RESTRICT",
    ),
    (
        "reliability_executions",
        "fk_reliability_executions_org_ingestion_batch",
        "ingestion_batches",
        "ingestion_batch_id",
        "RESTRICT",
    ),
    (
        "reliability_executions",
        "fk_reliability_executions_org_source_system",
        "source_systems",
        "source_system_id",
        "RESTRICT",
    ),
    (
        "reliability_executions",
        "fk_reliability_executions_org_trust_assessment",
        "trust_assessments",
        "trust_assessment_id",
        "RESTRICT",
    ),
    (
        "reliability_executions",
        "fk_reliability_executions_org_readiness",
        "analytical_readiness_decisions",
        "readiness_assessment_id",
        "RESTRICT",
    ),
    (
        "reliability_metrics",
        "fk_reliability_metrics_org_execution",
        "reliability_executions",
        "reliability_execution_id",
        "CASCADE",
    ),
    (
        "reliability_model_results",
        "fk_reliability_model_results_org_execution",
        "reliability_executions",
        "reliability_execution_id",
        "CASCADE",
    ),
    (
        "reliability_review_feedback",
        "fk_reliability_review_feedback_org_execution",
        "reliability_executions",
        "reliability_execution_id",
        "CASCADE",
    ),
    (
        "statistical_executions",
        "fk_statistical_executions_org_dataset",
        "datasets",
        "dataset_id",
        "RESTRICT",
    ),
    (
        "statistical_executions",
        "fk_statistical_executions_org_dataset_version",
        "dataset_versions",
        "dataset_version_id",
        "RESTRICT",
    ),
    (
        "statistical_executions",
        "fk_statistical_executions_org_ingestion_batch",
        "ingestion_batches",
        "ingestion_batch_id",
        "RESTRICT",
    ),
    (
        "statistical_executions",
        "fk_statistical_executions_org_source_system",
        "source_systems",
        "source_system_id",
        "RESTRICT",
    ),
    (
        "statistical_executions",
        "fk_statistical_executions_org_trust_assessment",
        "trust_assessments",
        "trust_assessment_id",
        "RESTRICT",
    ),
    (
        "statistical_executions",
        "fk_statistical_executions_org_readiness",
        "analytical_readiness_decisions",
        "readiness_assessment_id",
        "RESTRICT",
    ),
    (
        "statistical_baselines",
        "fk_statistical_baselines_org_execution",
        "statistical_executions",
        "statistical_execution_id",
        "CASCADE",
    ),
    (
        "statistical_observations",
        "fk_statistical_observations_org_execution",
        "statistical_executions",
        "statistical_execution_id",
        "CASCADE",
    ),
    (
        "anomaly_review_feedback",
        "fk_anomaly_review_feedback_org_observation",
        "statistical_observations",
        "statistical_observation_id",
        "CASCADE",
    ),
)

COMPOSITE_INDEXES = (
    ("reliability_executions", "ix_reliability_execution_org_dataset", "dataset_id"),
    (
        "reliability_executions",
        "ix_reliability_execution_org_dataset_version",
        "dataset_version_id",
    ),
    (
        "reliability_executions",
        "ix_reliability_execution_org_ingestion_batch",
        "ingestion_batch_id",
    ),
    (
        "reliability_executions",
        "ix_reliability_execution_org_source_system",
        "source_system_id",
    ),
    (
        "reliability_executions",
        "ix_reliability_execution_org_trust_assessment",
        "trust_assessment_id",
    ),
    (
        "reliability_executions",
        "ix_reliability_execution_org_readiness",
        "readiness_assessment_id",
    ),
    (
        "reliability_model_results",
        "ix_reliability_model_result_org_execution",
        "reliability_execution_id",
    ),
    ("statistical_executions", "ix_statistical_execution_org_dataset", "dataset_id"),
    (
        "statistical_executions",
        "ix_statistical_execution_org_dataset_version",
        "dataset_version_id",
    ),
    (
        "statistical_executions",
        "ix_statistical_execution_org_ingestion_batch",
        "ingestion_batch_id",
    ),
    (
        "statistical_executions",
        "ix_statistical_execution_org_source_system",
        "source_system_id",
    ),
    (
        "statistical_executions",
        "ix_statistical_execution_org_trust_assessment",
        "trust_assessment_id",
    ),
    (
        "statistical_executions",
        "ix_statistical_execution_org_readiness",
        "readiness_assessment_id",
    ),
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
