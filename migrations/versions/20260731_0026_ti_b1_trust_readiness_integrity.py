"""Enforce Trust and Analytical Readiness tenant referential integrity.

Revision ID: 20260731_0026
Revises: 20260731_0025
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

revision: str = "20260731_0026"
down_revision: str | None = "20260731_0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PARENT_UNIQUES = (
    ("trust_assessments", "uq_trust_assessments_org_id"),
    ("trust_rule_results", "uq_trust_rule_results_org_id"),
    (
        "analytical_readiness_decisions",
        "uq_analytical_readiness_decisions_org_id",
    ),
)

COMPOSITE_FOREIGN_KEYS = (
    (
        "trust_assessments",
        "fk_trust_assessments_org_dataset",
        "datasets",
        "dataset_id",
    ),
    (
        "trust_assessments",
        "fk_trust_assessments_org_ingestion_batch",
        "ingestion_batches",
        "ingestion_batch_id",
    ),
    (
        "trust_rule_results",
        "fk_trust_rule_results_org_trust_assessment",
        "trust_assessments",
        "trust_assessment_id",
    ),
    (
        "trust_evidence",
        "fk_trust_evidence_org_rule_result",
        "trust_rule_results",
        "trust_rule_result_id",
    ),
    (
        "trust_evidence",
        "fk_trust_evidence_org_dataset",
        "datasets",
        "dataset_id",
    ),
    (
        "analytical_readiness_decisions",
        "fk_readiness_org_trust_assessment",
        "trust_assessments",
        "trust_assessment_id",
    ),
)

COMPOSITE_INDEXES = (
    (
        "trust_assessments",
        "ix_trust_assessments_org_dataset_id",
        "dataset_id",
    ),
    (
        "trust_assessments",
        "ix_trust_assessments_org_ingestion_batch_id",
        "ingestion_batch_id",
    ),
    (
        "trust_rule_results",
        "ix_trust_rule_results_org_trust_assessment_id",
        "trust_assessment_id",
    ),
    (
        "trust_evidence",
        "ix_trust_evidence_org_rule_result_id",
        "trust_rule_result_id",
    ),
    (
        "trust_evidence",
        "ix_trust_evidence_org_dataset_id",
        "dataset_id",
    ),
    (
        "analytical_readiness_decisions",
        "ix_readiness_org_trust_assessment_id",
        "trust_assessment_id",
    ),
)


def _assert_clean_tenant_references() -> None:
    bind = op.get_bind()
    for child, constraint_name, parent, parent_column in COMPOSITE_FOREIGN_KEYS:
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

    for child, constraint_name, parent, parent_column in COMPOSITE_FOREIGN_KEYS:
        with op.batch_alter_table(child) as batch_op:
            batch_op.create_foreign_key(
                constraint_name,
                parent,
                ["organization_id", parent_column],
                ["organization_id", "id"],
                ondelete="RESTRICT",
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

    for child, constraint_name, _, _ in reversed(COMPOSITE_FOREIGN_KEYS):
        with op.batch_alter_table(child) as batch_op:
            batch_op.drop_constraint(constraint_name, type_="foreignkey")

    for table_name, constraint_name in reversed(PARENT_UNIQUES):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_constraint(constraint_name, type_="unique")
