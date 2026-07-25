"""Findings, evidence, and explainability platform.

Revision ID: 20260725_0008
Revises: 20260724_0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260725_0008"
down_revision: str | None = "20260724_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

portable_json = sa.JSON().with_variant(
    postgresql.JSONB(astext_type=sa.Text()),
    "postgresql",
)


def _finding_columns(*, include_foreign_keys: bool = True) -> list[sa.Column[object]]:
    def uuid_reference(name: str, target: str) -> sa.Column[object]:
        if not include_foreign_keys:
            return sa.Column(name, sa.Uuid(), nullable=True)
        return sa.Column(
            name,
            sa.Uuid(),
            sa.ForeignKey(target, ondelete="RESTRICT"),
            nullable=True,
        )

    return [
        sa.Column("finding_code", sa.String(length=100), nullable=True),
        sa.Column("finding_type", sa.String(length=30), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("domain_code", sa.String(length=100), nullable=True),
        sa.Column("process_code", sa.String(length=100), nullable=True),
        sa.Column("industry_pack_code", sa.String(length=100), nullable=True),
        sa.Column("severity_reason", portable_json, nullable=True),
        sa.Column("confidence_level", sa.String(length=30), nullable=True),
        sa.Column("confidence_method_code", sa.String(length=100), nullable=True),
        sa.Column("confidence_method_version", sa.String(length=30), nullable=True),
        sa.Column("confidence_components", portable_json, nullable=True),
        sa.Column("confidence_interpretation", sa.Text(), nullable=True),
        sa.Column("confidence_limitations", portable_json, nullable=True),
        sa.Column("measured_value", sa.Numeric(precision=38, scale=12), nullable=True),
        sa.Column("measured_value_type", sa.String(length=30), nullable=True),
        sa.Column("measured_unit", sa.String(length=50), nullable=True),
        sa.Column("measured_currency", sa.String(length=3), nullable=True),
        sa.Column("exposure_value", sa.Numeric(precision=38, scale=12), nullable=True),
        sa.Column("exposure_value_type", sa.String(length=30), nullable=True),
        sa.Column("exposure_currency", sa.String(length=3), nullable=True),
        sa.Column("affected_record_count", sa.Integer(), nullable=True),
        sa.Column("occurrence_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("occurrence_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        uuid_reference("superseded_by_finding_id", "findings.id"),
        uuid_reference("source_execution_id", "intelligence_executions.id"),
        uuid_reference("source_result_id", "intelligence_executions.id"),
        sa.Column("definition_code", sa.String(length=100), nullable=True),
        sa.Column("definition_version", sa.String(length=30), nullable=True),
        sa.Column("definition_fingerprint", sa.String(length=64), nullable=True),
        uuid_reference("trust_assessment_id", "trust_assessments.id"),
        uuid_reference("analytical_readiness_id", "analytical_readiness_decisions.id"),
        uuid_reference("dataset_id", "datasets.id"),
        sa.Column("dataset_reference", sa.String(length=255), nullable=True),
        sa.Column("warnings", portable_json, nullable=True),
        sa.Column("limitations", portable_json, nullable=True),
        sa.Column("content_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("deduplication_key", sa.String(length=64), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    for column in _finding_columns(include_foreign_keys=dialect != "sqlite"):
        op.add_column("findings", column)
    if dialect == "sqlite":
        with op.batch_alter_table("findings") as batch:
            batch.alter_column(
                "confidence_score",
                existing_type=sa.Float(),
                type_=sa.Numeric(precision=6, scale=4),
                existing_nullable=False,
            )
    else:
        op.alter_column(
            "findings",
            "confidence_score",
            existing_type=sa.Float(),
            type_=sa.Numeric(precision=6, scale=4),
            existing_nullable=False,
            postgresql_using="confidence_score::numeric(6,4)",
        )
        op.create_check_constraint(
            "ck_findings_confidence_score",
            "findings",
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)",
        )
        op.create_check_constraint(
            "ck_findings_affected_record_count",
            "findings",
            "affected_record_count >= 0",
        )
    for name, columns, unique in (
        (
            "uq_findings_organization_deduplication",
            ["organization_id", "deduplication_key"],
            True,
        ),
        ("ix_findings_organization_status", ["organization_id", "status"], False),
        ("ix_findings_organization_type", ["organization_id", "finding_type"], False),
        ("ix_findings_organization_severity", ["organization_id", "severity"], False),
        ("ix_findings_organization_detected", ["organization_id", "detected_at"], False),
        (
            "ix_findings_organization_occurrence",
            ["organization_id", "occurrence_start"],
            False,
        ),
        (
            "ix_findings_source_execution",
            ["organization_id", "source_execution_id"],
            False,
        ),
        (
            "ix_findings_definition",
            ["organization_id", "definition_code", "definition_version"],
            False,
        ),
    ):
        op.create_index(name, "findings", columns, unique=unique)

    op.create_table(
        "finding_evidence_bundles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("finding_id", sa.Uuid(), nullable=False),
        sa.Column("bundle_version", sa.Integer(), nullable=False),
        sa.Column("evidence_policy_code", sa.String(length=100), nullable=False),
        sa.Column("evidence_policy_version", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("completeness_status", sa.String(length=30), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('open', 'complete', 'incomplete', 'invalid', 'superseded')",
            name="ck_finding_evidence_bundle_status",
        ),
        sa.CheckConstraint(
            "completeness_status IN ('complete', 'incomplete', 'invalid')",
            name="ck_finding_evidence_bundle_completeness",
        ),
        sa.ForeignKeyConstraint(["finding_id"], ["findings.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "finding_id",
            "bundle_version",
            name="uq_finding_evidence_bundle_version",
        ),
    )
    op.create_index(
        "ix_finding_evidence_bundles_organization_id",
        "finding_evidence_bundles",
        ["organization_id"],
    )
    op.create_index(
        "ix_finding_evidence_bundles_finding_id",
        "finding_evidence_bundles",
        ["finding_id"],
    )

    op.create_table(
        "finding_evidence_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_bundle_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_type", sa.String(length=40), nullable=False),
        sa.Column("reference_type", sa.String(length=50), nullable=False),
        sa.Column("reference_id", sa.String(length=255), nullable=True),
        sa.Column("reference_uri", sa.String(length=500), nullable=True),
        sa.Column("reference_fingerprint", sa.String(length=128), nullable=True),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_system_id", sa.Uuid(), nullable=True),
        sa.Column("ingestion_batch_id", sa.Uuid(), nullable=True),
        sa.Column("dataset_id", sa.Uuid(), nullable=True),
        sa.Column("lineage_node_id", sa.Uuid(), nullable=True),
        sa.Column("raw_record_reference_id", sa.Uuid(), nullable=True),
        sa.Column("canonical_entity", sa.String(length=100), nullable=True),
        sa.Column("canonical_record_reference", sa.String(length=255), nullable=True),
        sa.Column("field_reference", sa.String(length=150), nullable=True),
        sa.Column("comparison_value", sa.Numeric(precision=38, scale=12), nullable=True),
        sa.Column("comparison_unit", sa.String(length=50), nullable=True),
        sa.Column("comparison_currency", sa.String(length=3), nullable=True),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("metadata_json", portable_json, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "sequence_number > 0",
            name="ck_finding_evidence_item_sequence",
        ),
        sa.CheckConstraint(
            "reference_id IS NOT NULL OR reference_uri IS NOT NULL OR "
            "canonical_record_reference IS NOT NULL",
            name="ck_finding_evidence_item_reference",
        ),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["evidence_bundle_id"],
            ["finding_evidence_bundles.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ingestion_batch_id"], ["ingestion_batches.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["lineage_node_id"], ["lineage_nodes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["raw_record_reference_id"],
            ["raw_record_references.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["source_system_id"], ["source_systems.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "evidence_bundle_id",
            "sequence_number",
            name="uq_finding_evidence_item_sequence",
        ),
    )
    for name, columns in (
        ("ix_finding_evidence_items_organization_id", ["organization_id"]),
        ("ix_finding_evidence_items_bundle_id", ["evidence_bundle_id"]),
        (
            "ix_finding_evidence_items_reference",
            ["reference_type", "reference_id"],
        ),
    ):
        op.create_index(name, "finding_evidence_items", columns)

    _create_trace_tables()
    _create_review_tables()


def _create_trace_tables() -> None:
    op.create_table(
        "finding_calculation_traces",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("finding_id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.Uuid(), nullable=False),
        sa.Column("definition_code", sa.String(length=100), nullable=False),
        sa.Column("definition_version", sa.String(length=30), nullable=False),
        sa.Column("engine_version", sa.String(length=30), nullable=False),
        sa.Column("operation_code", sa.String(length=100), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("input_reference_summary", portable_json, nullable=False),
        sa.Column("parameter_summary", portable_json, nullable=False),
        sa.Column("output_value", sa.Numeric(precision=38, scale=12), nullable=True),
        sa.Column("output_type", sa.String(length=30), nullable=False),
        sa.Column("output_unit", sa.String(length=50), nullable=True),
        sa.Column("output_currency", sa.String(length=3), nullable=True),
        sa.Column("warnings", portable_json, nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "sequence_number > 0",
            name="ck_finding_calculation_trace_sequence",
        ),
        sa.ForeignKeyConstraint(
            ["execution_id"], ["intelligence_executions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["finding_id"], ["findings.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "finding_id",
            "sequence_number",
            name="uq_finding_calculation_trace_sequence",
        ),
    )
    for name, columns in (
        ("ix_finding_calculation_traces_organization_id", ["organization_id"]),
        ("ix_finding_calculation_traces_finding_id", ["finding_id"]),
        ("ix_finding_calculation_traces_execution_id", ["execution_id"]),
    ):
        op.create_index(name, "finding_calculation_traces", columns)

    op.create_table(
        "finding_rule_traces",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("finding_id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.Uuid(), nullable=False),
        sa.Column("rule_code", sa.String(length=100), nullable=False),
        sa.Column("rule_version", sa.String(length=30), nullable=False),
        sa.Column("condition_code", sa.String(length=100), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("evaluation_result", sa.Boolean(), nullable=False),
        sa.Column("operand_reference_summary", portable_json, nullable=False),
        sa.Column("comparison_operator", sa.String(length=50), nullable=False),
        sa.Column("threshold_summary", portable_json, nullable=False),
        sa.Column("warnings", portable_json, nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "sequence_number > 0",
            name="ck_finding_rule_trace_sequence",
        ),
        sa.ForeignKeyConstraint(
            ["execution_id"], ["intelligence_executions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["finding_id"], ["findings.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "finding_id",
            "sequence_number",
            name="uq_finding_rule_trace_sequence",
        ),
    )
    for name, columns in (
        ("ix_finding_rule_traces_organization_id", ["organization_id"]),
        ("ix_finding_rule_traces_finding_id", ["finding_id"]),
        ("ix_finding_rule_traces_execution_id", ["execution_id"]),
    ):
        op.create_index(name, "finding_rule_traces", columns)


def _create_review_tables() -> None:
    op.create_table(
        "finding_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("finding_id", sa.Uuid(), nullable=False),
        sa.Column("review_status", sa.String(length=30), nullable=False),
        sa.Column("decision", sa.String(length=40), nullable=False),
        sa.Column("reviewer_user_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_role", sa.String(length=50), nullable=False),
        sa.Column("reason_code", sa.String(length=100), nullable=False),
        sa.Column("comments", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["finding_id"], ["findings.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in (
        ("ix_finding_reviews_organization_id", ["organization_id"]),
        ("ix_finding_reviews_finding_id", ["finding_id"]),
        ("ix_finding_reviews_reviewed_at", ["reviewed_at"]),
    ):
        op.create_index(name, "finding_reviews", columns)

    op.create_table(
        "finding_status_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("finding_id", sa.Uuid(), nullable=False),
        sa.Column("previous_status", sa.String(length=30), nullable=True),
        sa.Column("new_status", sa.String(length=30), nullable=False),
        sa.Column("reason_code", sa.String(length=100), nullable=False),
        sa.Column("changed_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata_json", portable_json, nullable=False),
        sa.ForeignKeyConstraint(["finding_id"], ["findings.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in (
        ("ix_finding_status_history_organization_id", ["organization_id"]),
        ("ix_finding_status_history_finding_id", ["finding_id"]),
        ("ix_finding_status_history_changed_at", ["changed_at"]),
    ):
        op.create_index(name, "finding_status_history", columns)


def downgrade() -> None:
    for table, indexes in (
        (
            "finding_status_history",
            (
                "ix_finding_status_history_changed_at",
                "ix_finding_status_history_finding_id",
                "ix_finding_status_history_organization_id",
            ),
        ),
        (
            "finding_reviews",
            (
                "ix_finding_reviews_reviewed_at",
                "ix_finding_reviews_finding_id",
                "ix_finding_reviews_organization_id",
            ),
        ),
        (
            "finding_rule_traces",
            (
                "ix_finding_rule_traces_execution_id",
                "ix_finding_rule_traces_finding_id",
                "ix_finding_rule_traces_organization_id",
            ),
        ),
        (
            "finding_calculation_traces",
            (
                "ix_finding_calculation_traces_execution_id",
                "ix_finding_calculation_traces_finding_id",
                "ix_finding_calculation_traces_organization_id",
            ),
        ),
        (
            "finding_evidence_items",
            (
                "ix_finding_evidence_items_reference",
                "ix_finding_evidence_items_bundle_id",
                "ix_finding_evidence_items_organization_id",
            ),
        ),
        (
            "finding_evidence_bundles",
            (
                "ix_finding_evidence_bundles_finding_id",
                "ix_finding_evidence_bundles_organization_id",
            ),
        ),
    ):
        for index in indexes:
            op.drop_index(index, table_name=table)
        op.drop_table(table)

    for name in (
        "ix_findings_definition",
        "ix_findings_source_execution",
        "ix_findings_organization_occurrence",
        "ix_findings_organization_detected",
        "ix_findings_organization_severity",
        "ix_findings_organization_type",
        "ix_findings_organization_status",
        "uq_findings_organization_deduplication",
    ):
        op.drop_index(name, table_name="findings")
    dialect = op.get_bind().dialect.name
    if dialect != "sqlite":
        op.drop_constraint(
            "ck_findings_affected_record_count",
            "findings",
            type_="check",
        )
        op.drop_constraint(
            "ck_findings_confidence_score",
            "findings",
            type_="check",
        )
    for column in reversed(_finding_columns(include_foreign_keys=False)):
        op.drop_column("findings", column.name)
    if dialect == "sqlite":
        with op.batch_alter_table("findings") as batch:
            batch.alter_column(
                "confidence_score",
                existing_type=sa.Numeric(precision=6, scale=4),
                type_=sa.Float(),
                existing_nullable=False,
            )
    else:
        op.alter_column(
            "findings",
            "confidence_score",
            existing_type=sa.Numeric(precision=6, scale=4),
            type_=sa.Float(),
            existing_nullable=False,
            postgresql_using="confidence_score::double precision",
        )
