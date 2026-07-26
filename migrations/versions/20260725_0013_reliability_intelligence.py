"""governed reliability intelligence engine

Revision ID: 20260725_0013
Revises: 20260725_0012
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.models.source_system import portable_json

revision: str = "20260725_0013"
down_revision: str | None = "20260725_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("analytical_readiness_decisions") as batch:
        batch.drop_constraint("ck_readiness_level", type_="check")
        batch.create_check_constraint(
            "ck_readiness_level",
            "analytical_level IN ('arithmetic','statistical','forecasting','reliability',"
            "'predictive','optimization','economic_recovery')",
        )
    op.create_table(
        "reliability_method_registry",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("method_code", sa.String(100), nullable=False),
        sa.Column("method_name", sa.String(200), nullable=False),
        sa.Column("method_version", sa.String(30), nullable=False),
        sa.Column("capability_class", sa.String(80), nullable=False),
        sa.Column("supported", sa.Boolean(), nullable=False),
        sa.Column("minimum_failure_count", sa.Integer(), nullable=False),
        sa.Column("minimum_asset_count", sa.Integer(), nullable=False),
        sa.Column("minimum_exposure", sa.Numeric(38, 12), nullable=False),
        sa.Column("supports_censoring", sa.Boolean(), nullable=False),
        sa.Column("supports_grouped_assets", sa.Boolean(), nullable=False),
        sa.Column("supports_condition_inputs", sa.Boolean(), nullable=False),
        sa.Column("supports_uncertainty", sa.Boolean(), nullable=False),
        sa.Column("parameter_schema", portable_json, nullable=False),
        sa.Column("input_schema", portable_json, nullable=False),
        sa.Column("output_schema", portable_json, nullable=False),
        sa.Column("implementation_reference", sa.String(300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("method_code", "method_version", name="uq_reliability_method_version"),
    )
    op.create_table(
        "reliability_executions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("orchestration_request_id", sa.Uuid(), nullable=True),
        sa.Column("oikb_definition_id", sa.Uuid(), nullable=False),
        sa.Column("oikb_definition_version_id", sa.Uuid(), nullable=False),
        sa.Column("trust_assessment_id", sa.Uuid(), nullable=False),
        sa.Column("readiness_assessment_id", sa.Uuid(), nullable=False),
        sa.Column("execution_package_fingerprint", sa.String(64), nullable=False),
        sa.Column("reproducibility_fingerprint", sa.String(64), nullable=False),
        sa.Column("asset_scope_reference", sa.String(255), nullable=False),
        sa.Column("asset_scope_type", sa.String(40), nullable=False),
        sa.Column("reliability_method_code", sa.String(100), nullable=False),
        sa.Column("reliability_method_version", sa.String(30), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("dataset_reference", sa.String(255), nullable=False),
        sa.Column("dataset_fingerprint", sa.String(64), nullable=False),
        sa.Column("lifecycle_fingerprint", sa.String(64), nullable=False),
        sa.Column("source_lineage_reference", sa.String(500), nullable=False),
        sa.Column("observation_window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observation_window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exposure_basis", sa.String(40), nullable=False),
        sa.Column("exposure_unit", sa.String(50), nullable=False),
        sa.Column("failure_definition_code", sa.String(100), nullable=False),
        sa.Column("failure_definition_version", sa.String(30), nullable=False),
        sa.Column("censoring_policy", sa.String(50), nullable=False),
        sa.Column("engine_version", sa.String(30), nullable=False),
        sa.Column("correlation_id", sa.String(100), nullable=False),
        sa.Column("explanation", portable_json, nullable=False),
        sa.Column("warnings", portable_json, nullable=False),
        sa.Column("limitations", portable_json, nullable=False),
        sa.Column("failure_code", sa.String(100)),
        sa.Column("failure_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["orchestration_request_id"],
            ["intelligence_orchestration_requests.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["oikb_definition_id"], ["oikb_definitions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["oikb_definition_version_id"], ["oikb_definition_versions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["trust_assessment_id"], ["trust_assessments.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["readiness_assessment_id"],
            ["analytical_readiness_decisions.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "organization_id", "reproducibility_fingerprint", name="uq_reliability_reproducibility"
        ),
        sa.CheckConstraint(
            "status IN ('pending','running','succeeded','blocked','not_ready',"
            "'insufficient_data','unsupported','failed','cancelled')",
            name="ck_reliability_execution_status",
        ),
    )
    op.create_index(
        "ix_reliability_execution_org_status",
        "reliability_executions",
        ["organization_id", "status"],
    )
    op.create_index(
        "ix_reliability_execution_asset_scope",
        "reliability_executions",
        ["organization_id", "asset_scope_reference"],
    )
    op.create_table(
        "reliability_metrics",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("reliability_execution_id", sa.Uuid(), nullable=False),
        sa.Column("asset_reference", sa.String(255)),
        sa.Column("metric_code", sa.String(100), nullable=False),
        sa.Column("metric_value", sa.Numeric(38, 12)),
        sa.Column("metric_unit", sa.String(50), nullable=False),
        sa.Column("numerator_value", sa.Numeric(38, 12)),
        sa.Column("denominator_value", sa.Numeric(38, 12)),
        sa.Column("exposure_basis", sa.String(40), nullable=False),
        sa.Column("confidence_score", sa.Numeric(8, 5), nullable=False),
        sa.Column("materiality_score", sa.Numeric(8, 5)),
        sa.Column("valid", sa.Boolean(), nullable=False),
        sa.Column("invalid_reason", sa.String(100)),
        sa.Column("method_trace", portable_json, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["reliability_execution_id"], ["reliability_executions.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_reliability_metric_org_execution",
        "reliability_metrics",
        ["organization_id", "reliability_execution_id"],
    )
    op.create_table(
        "reliability_model_results",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("reliability_execution_id", sa.Uuid(), nullable=False),
        sa.Column("asset_reference", sa.String(255)),
        sa.Column("method_code", sa.String(100), nullable=False),
        sa.Column("method_version", sa.String(30), nullable=False),
        sa.Column("parameter_values", portable_json, nullable=False),
        sa.Column("fit_diagnostics", portable_json, nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.Column("censored_count", sa.Integer(), nullable=False),
        sa.Column("validation_status", sa.String(40), nullable=False),
        sa.Column("limitations", portable_json, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["reliability_execution_id"], ["reliability_executions.id"], ondelete="CASCADE"
        ),
    )
    op.create_table(
        "reliability_execution_steps",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("reliability_execution_id", sa.Uuid(), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("step_code", sa.String(100), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("input_summary", portable_json, nullable=False),
        sa.Column("output_summary", portable_json, nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["reliability_execution_id"], ["reliability_executions.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "reliability_execution_id", "sequence_number", name="uq_reliability_step_sequence"
        ),
    )
    op.create_table(
        "reliability_review_feedback",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("reliability_execution_id", sa.Uuid(), nullable=False),
        sa.Column("assessment_type", sa.String(50), nullable=False),
        sa.Column("assessment_reference", sa.String(255), nullable=False),
        sa.Column("review_status", sa.String(40), nullable=False),
        sa.Column("reviewer_id", sa.Uuid(), nullable=False),
        sa.Column("was_actionable", sa.Boolean(), nullable=False),
        sa.Column("was_false_positive", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["reliability_execution_id"], ["reliability_executions.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_reliability_review_org_execution",
        "reliability_review_feedback",
        ["organization_id", "reliability_execution_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_reliability_review_org_execution", table_name="reliability_review_feedback")
    op.drop_table("reliability_review_feedback")
    op.drop_table("reliability_execution_steps")
    op.drop_table("reliability_model_results")
    op.drop_index("ix_reliability_metric_org_execution", table_name="reliability_metrics")
    op.drop_table("reliability_metrics")
    op.drop_index("ix_reliability_execution_asset_scope", table_name="reliability_executions")
    op.drop_index("ix_reliability_execution_org_status", table_name="reliability_executions")
    op.drop_table("reliability_executions")
    op.drop_table("reliability_method_registry")
    op.execute(
        sa.text(
            "UPDATE analytical_readiness_decisions "
            "SET analytical_level = 'predictive' "
            "WHERE analytical_level = 'reliability'"
        )
    )
    with op.batch_alter_table("analytical_readiness_decisions") as batch:
        batch.drop_constraint("ck_readiness_level", type_="check")
        batch.create_check_constraint(
            "ck_readiness_level",
            "analytical_level IN ('arithmetic','statistical','forecasting','predictive',"
            "'optimization','economic_recovery')",
        )
