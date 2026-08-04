"""Enforce Action Workflow tenant referential integrity.

Revision ID: 20260802_0030
Revises: 20260801_0029
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

revision: str = "20260802_0030"
down_revision: str | None = "20260801_0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PARENT_UNIQUES = (("operational_actions", "uq_operational_actions_org_id"),)

COMPOSITE_FOREIGN_KEYS = (
    (
        "action_plan_steps",
        "fk_action_plan_steps_org_action",
        "operational_actions",
        "action_id",
        "CASCADE",
    ),
    (
        "action_dependencies",
        "fk_action_dependencies_org_action",
        "operational_actions",
        "action_id",
        "CASCADE",
    ),
    (
        "action_dependencies",
        "fk_action_dependencies_org_prerequisite",
        "operational_actions",
        "prerequisite_action_id",
        "RESTRICT",
    ),
    (
        "action_resource_requirements",
        "fk_action_resource_requirements_org_action",
        "operational_actions",
        "action_id",
        "CASCADE",
    ),
    (
        "action_events",
        "fk_action_events_org_action",
        "operational_actions",
        "action_id",
        "CASCADE",
    ),
    (
        "action_evidence",
        "fk_action_evidence_org_action",
        "operational_actions",
        "action_id",
        "CASCADE",
    ),
    (
        "action_outcomes",
        "fk_action_outcomes_org_action",
        "operational_actions",
        "action_id",
        "CASCADE",
    ),
    (
        "action_model_feedback",
        "fk_action_model_feedback_org_action",
        "operational_actions",
        "action_id",
        "CASCADE",
    ),
    (
        "action_model_feedback",
        "fk_action_model_feedback_org_reliability_execution",
        "reliability_executions",
        "reliability_execution_id",
        "RESTRICT",
    ),
    (
        "operational_actions",
        "fk_operational_actions_org_reliability_execution",
        "reliability_executions",
        "reliability_execution_id",
        "RESTRICT",
    ),
    (
        "operational_actions",
        "fk_operational_actions_org_forecast_execution",
        "forecast_executions",
        "forecast_execution_id",
        "RESTRICT",
    ),
    (
        "operational_actions",
        "fk_operational_actions_org_orchestration_request",
        "intelligence_orchestration_requests",
        "orchestration_request_id",
        "RESTRICT",
    ),
)

COMPOSITE_INDEXES = (
    (
        "action_dependencies",
        "ix_action_dependency_org_prerequisite",
        "prerequisite_action_id",
    ),
    (
        "action_model_feedback",
        "ix_action_feedback_org_reliability_execution",
        "reliability_execution_id",
    ),
    (
        "operational_actions",
        "ix_action_org_reliability_execution",
        "reliability_execution_id",
    ),
    (
        "operational_actions",
        "ix_action_org_forecast_execution",
        "forecast_execution_id",
    ),
    (
        "operational_actions",
        "ix_action_org_orchestration_request",
        "orchestration_request_id",
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
                f"{constraint_name} precondition failed with {violations} tenant violations"
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


def _unique_exists(table_name: str, constraint_name: str) -> bool:
    return any(
        constraint["name"] == constraint_name
        for constraint in sa.inspect(op.get_bind()).get_unique_constraints(table_name)
    )


def _foreign_key_exists(table_name: str, constraint_name: str) -> bool:
    return any(
        constraint["name"] == constraint_name
        for constraint in sa.inspect(op.get_bind()).get_foreign_keys(table_name)
    )


def _index_exists(table_name: str, index_name: str) -> bool:
    return any(
        index["name"] == index_name for index in sa.inspect(op.get_bind()).get_indexes(table_name)
    )


def upgrade() -> None:
    offline = context.is_offline_mode()
    if not offline:
        _assert_clean_tenant_references()

    for table_name, constraint_name in PARENT_UNIQUES:
        if not offline and _unique_exists(table_name, constraint_name):
            continue
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.create_unique_constraint(
                constraint_name,
                ["organization_id", "id"],
            )

    for child, constraint_name, parent, parent_column, ondelete in COMPOSITE_FOREIGN_KEYS:
        if not offline and _foreign_key_exists(child, constraint_name):
            continue
        with op.batch_alter_table(child) as batch_op:
            batch_op.create_foreign_key(
                constraint_name,
                parent,
                ["organization_id", parent_column],
                ["organization_id", "id"],
                ondelete=ondelete,
            )

    for table_name, index_name, parent_column in COMPOSITE_INDEXES:
        if not offline and _index_exists(table_name, index_name):
            continue
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
