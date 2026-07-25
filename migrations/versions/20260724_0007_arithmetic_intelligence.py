"""Arithmetic and deterministic rule intelligence foundation.

Revision ID: 20260724_0007
Revises: 20260724_0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260724_0007"
down_revision: str | None = "20260724_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

portable_json = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "intelligence_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_version_id", sa.Uuid(), nullable=True),
        sa.Column("trust_assessment_id", sa.Uuid(), nullable=False),
        sa.Column("readiness_decision_id", sa.Uuid(), nullable=False),
        sa.Column("execution_type", sa.String(length=30), nullable=False),
        sa.Column("definition_code", sa.String(length=100), nullable=False),
        sa.Column("definition_version", sa.String(length=30), nullable=False),
        sa.Column("definition_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("parameters_json", portable_json, nullable=False),
        sa.Column("result_value", sa.Numeric(precision=38, scale=12), nullable=True),
        sa.Column("comparison_value", sa.Numeric(precision=38, scale=12), nullable=True),
        sa.Column("threshold_value", sa.Numeric(precision=38, scale=12), nullable=True),
        sa.Column("unit", sa.String(length=50), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("breached", sa.Boolean(), nullable=True),
        sa.Column("checked_record_count", sa.Integer(), nullable=False),
        sa.Column("excluded_record_count", sa.Integer(), nullable=False),
        sa.Column("affected_record_count", sa.Integer(), nullable=False),
        sa.Column("exposure_value", sa.Numeric(precision=38, scale=12), nullable=True),
        sa.Column("exposure_currency", sa.String(length=3), nullable=True),
        sa.Column("blocking_rule_codes", portable_json, nullable=False),
        sa.Column("warning_rule_codes", portable_json, nullable=False),
        sa.Column("warnings", portable_json, nullable=False),
        sa.Column("limitations", portable_json, nullable=False),
        sa.Column("non_execution_reason", sa.Text(), nullable=True),
        sa.Column("input_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("input_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evaluation_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "checked_record_count >= 0 AND excluded_record_count >= 0 AND "
            "affected_record_count >= 0 AND affected_record_count <= checked_record_count",
            name="ck_intelligence_execution_counts",
        ),
        sa.CheckConstraint(
            "status IN ('completed', 'blocked', 'failed')",
            name="ck_intelligence_execution_status",
        ),
        sa.CheckConstraint(
            "execution_type IN ('calculation', 'rule')",
            name="ck_intelligence_execution_type",
        ),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"], ["dataset_versions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["readiness_decision_id"],
            ["analytical_readiness_decisions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["trust_assessment_id"], ["trust_assessments.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_intelligence_executions_organization_idempotency",
        ),
    )
    for name, columns in (
        ("ix_intelligence_executions_organization_id", ["organization_id"]),
        ("ix_intelligence_executions_dataset_id", ["dataset_id"]),
        ("ix_intelligence_executions_trust_assessment_id", ["trust_assessment_id"]),
        (
            "ix_intelligence_executions_definition",
            ["definition_code", "definition_version"],
        ),
        ("ix_intelligence_executions_status", ["status"]),
        ("ix_intelligence_executions_created_at", ["created_at"]),
    ):
        op.create_index(name, "intelligence_executions", columns, unique=False)

    op.create_table(
        "intelligence_execution_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.Uuid(), nullable=False),
        sa.Column("raw_record_reference_id", sa.Uuid(), nullable=True),
        sa.Column("lineage_node_id", sa.Uuid(), nullable=True),
        sa.Column("canonical_record_identifier", sa.String(length=255), nullable=True),
        sa.Column("aggregate_reference", portable_json, nullable=True),
        sa.Column("contributing_record_count", sa.Integer(), nullable=False),
        sa.Column("excluded_record_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "contributing_record_count >= 0 AND excluded_record_count >= 0",
            name="ck_intelligence_evidence_counts",
        ),
        sa.CheckConstraint(
            "raw_record_reference_id IS NOT NULL OR lineage_node_id IS NOT NULL OR "
            "canonical_record_identifier IS NOT NULL OR aggregate_reference IS NOT NULL",
            name="ck_intelligence_evidence_reference",
        ),
        sa.ForeignKeyConstraint(
            ["execution_id"], ["intelligence_executions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["lineage_node_id"], ["lineage_nodes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["raw_record_reference_id"],
            ["raw_record_references.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in (
        ("ix_intelligence_evidence_organization_id", ["organization_id"]),
        ("ix_intelligence_evidence_execution_id", ["execution_id"]),
        ("ix_intelligence_evidence_raw_record_id", ["raw_record_reference_id"]),
        ("ix_intelligence_evidence_lineage_node_id", ["lineage_node_id"]),
    ):
        op.create_index(name, "intelligence_execution_evidence", columns, unique=False)


def downgrade() -> None:
    for name in (
        "ix_intelligence_evidence_lineage_node_id",
        "ix_intelligence_evidence_raw_record_id",
        "ix_intelligence_evidence_execution_id",
        "ix_intelligence_evidence_organization_id",
    ):
        op.drop_index(name, table_name="intelligence_execution_evidence")
    op.drop_table("intelligence_execution_evidence")
    for name in (
        "ix_intelligence_executions_created_at",
        "ix_intelligence_executions_status",
        "ix_intelligence_executions_definition",
        "ix_intelligence_executions_trust_assessment_id",
        "ix_intelligence_executions_dataset_id",
        "ix_intelligence_executions_organization_id",
    ):
        op.drop_index(name, table_name="intelligence_executions")
    op.drop_table("intelligence_executions")
