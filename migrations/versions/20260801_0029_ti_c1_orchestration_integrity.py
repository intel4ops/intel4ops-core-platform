"""Enforce Orchestration tenant referential integrity.

Revision ID: 20260801_0029
Revises: 20260801_0028
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

revision: str = "20260801_0029"
down_revision: str | None = "20260801_0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PARENT_UNIQUES = (("intelligence_orchestration_requests", "uq_orchestration_requests_org_id"),)

COMPOSITE_FOREIGN_KEYS = (
    (
        "intelligence_orchestration_decisions",
        "fk_orchestration_decisions_org_request",
        "intelligence_orchestration_requests",
        "orchestration_request_id",
        "CASCADE",
    ),
    (
        "intelligence_orchestration_steps",
        "fk_orchestration_steps_org_request",
        "intelligence_orchestration_requests",
        "orchestration_request_id",
        "CASCADE",
    ),
    (
        "intelligence_orchestration_status_history",
        "fk_orchestration_history_org_request",
        "intelligence_orchestration_requests",
        "orchestration_request_id",
        "CASCADE",
    ),
    (
        "intelligence_orchestration_requests",
        "fk_orchestration_requests_org_dataset",
        "datasets",
        "dataset_id",
        "RESTRICT",
    ),
    (
        "intelligence_orchestration_requests",
        "fk_orchestration_requests_org_dataset_version",
        "dataset_versions",
        "dataset_version_id",
        "RESTRICT",
    ),
    (
        "intelligence_orchestration_requests",
        "fk_orchestration_requests_org_trust_assessment",
        "trust_assessments",
        "trust_assessment_id",
        "RESTRICT",
    ),
    (
        "intelligence_orchestration_requests",
        "fk_orchestration_requests_org_readiness",
        "analytical_readiness_decisions",
        "analytical_readiness_id",
        "RESTRICT",
    ),
    (
        "reliability_executions",
        "fk_reliability_executions_org_orchestration_request",
        "intelligence_orchestration_requests",
        "orchestration_request_id",
        "RESTRICT",
    ),
    (
        "statistical_executions",
        "fk_statistical_executions_org_orchestration_request",
        "intelligence_orchestration_requests",
        "orchestration_request_id",
        "RESTRICT",
    ),
    (
        "forecast_executions",
        "fk_forecast_executions_org_orchestration_request",
        "intelligence_orchestration_requests",
        "orchestration_request_id",
        "RESTRICT",
    ),
)

COMPOSITE_INDEXES = (
    (
        "intelligence_orchestration_requests",
        "ix_orchestration_requests_org_dataset",
        "dataset_id",
    ),
    (
        "intelligence_orchestration_requests",
        "ix_orchestration_requests_org_dataset_version",
        "dataset_version_id",
    ),
    (
        "intelligence_orchestration_requests",
        "ix_orchestration_requests_org_trust_assessment",
        "trust_assessment_id",
    ),
    (
        "intelligence_orchestration_requests",
        "ix_orchestration_requests_org_readiness",
        "analytical_readiness_id",
    ),
    (
        "reliability_executions",
        "ix_reliability_execution_org_orchestration_request",
        "orchestration_request_id",
    ),
    (
        "statistical_executions",
        "ix_statistical_execution_org_orchestration_request",
        "orchestration_request_id",
    ),
    (
        "forecast_executions",
        "ix_forecast_execution_org_orchestration_request",
        "orchestration_request_id",
    ),
)

LEGACY_ORCHESTRATION_FOREIGN_KEYS = (
    (
        "reliability_executions",
        "reliability_executions_orchestration_request_id_fkey",
    ),
    (
        "statistical_executions",
        "statistical_executions_orchestration_request_id_fkey",
    ),
    (
        "forecast_executions",
        "forecast_executions_orchestration_request_id_fkey",
    ),
)

SQLITE_NAMING_CONVENTION = {
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
}


def _legacy_foreign_key_name(table_name: str, postgresql_name: str) -> str:
    if op.get_bind().dialect.name == "sqlite":
        return f"fk_{table_name}_orchestration_request_id_intelligence_orchestration_requests"
    return postgresql_name


def _batch_options() -> dict[str, object]:
    if op.get_bind().dialect.name == "sqlite":
        return {"naming_convention": SQLITE_NAMING_CONVENTION}
    return {}


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

    for table_name, postgresql_name in LEGACY_ORCHESTRATION_FOREIGN_KEYS:
        with op.batch_alter_table(table_name, **_batch_options()) as batch_op:
            batch_op.drop_constraint(
                _legacy_foreign_key_name(table_name, postgresql_name),
                type_="foreignkey",
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

    for table_name, postgresql_name in reversed(LEGACY_ORCHESTRATION_FOREIGN_KEYS):
        with op.batch_alter_table(table_name, **_batch_options()) as batch_op:
            batch_op.create_foreign_key(
                _legacy_foreign_key_name(table_name, postgresql_name),
                "intelligence_orchestration_requests",
                ["orchestration_request_id"],
                ["id"],
                ondelete="SET NULL",
            )

    for table_name, constraint_name in reversed(PARENT_UNIQUES):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_constraint(constraint_name, type_="unique")
