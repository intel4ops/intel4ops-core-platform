"""predictive-to-action orchestration and closed-loop execution

Revision ID: 20260725_0014
Revises: 20260725_0013
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260725_0014"
down_revision: str | None = "20260725_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACTION_TABLES = (
    "operational_actions",
    "action_plan_steps",
    "action_dependencies",
    "action_resource_requirements",
    "action_events",
    "action_evidence",
    "action_outcomes",
    "action_model_feedback",
)

PORTABLE_JSON = sa.JSON().with_variant(
    postgresql.JSONB(astext_type=sa.Text()),
    "postgresql",
)

ACTION_STATUSES = (
    "proposed",
    "pending_approval",
    "approved",
    "rejected",
    "assigned",
    "scheduled",
    "in_progress",
    "blocked",
    "completed",
    "verification_pending",
    "verified",
    "verification_rejected",
    "cancelled",
)


def _status_check() -> str:
    values = ", ".join(f"'{value}'" for value in ACTION_STATUSES)
    return f"status IN ({values})"


def upgrade() -> None:
    op.create_table(
        "operational_actions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("source_reference", sa.String(length=255), nullable=False),
        sa.Column("reliability_execution_id", sa.Uuid(), nullable=True),
        sa.Column("finding_id", sa.Uuid(), nullable=True),
        sa.Column("forecast_execution_id", sa.Uuid(), nullable=True),
        sa.Column("orchestration_request_id", sa.Uuid(), nullable=True),
        sa.Column("recommendation_type", sa.String(length=80), nullable=False),
        sa.Column("recommendation_rule_version", sa.String(length=30), nullable=False),
        sa.Column("title", sa.String(length=250), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("asset_reference", sa.String(length=255), nullable=True),
        sa.Column("component_reference", sa.String(length=255), nullable=True),
        sa.Column("failure_mode", sa.String(length=150), nullable=True),
        sa.Column("priority", sa.String(length=20), nullable=False),
        sa.Column("priority_score", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("priority_components", PORTABLE_JSON, nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("approval_required", sa.Boolean(), nullable=False),
        sa.Column("approval_level", sa.String(length=50), nullable=False),
        sa.Column("approval_role", sa.String(length=50), nullable=False),
        sa.Column("approval_status", sa.String(length=40), nullable=False),
        sa.Column("assigned_user_id", sa.Uuid(), nullable=True),
        sa.Column("assigned_role", sa.String(length=50), nullable=True),
        sa.Column("assigned_team", sa.String(length=150), nullable=True),
        sa.Column("verification_required", sa.Boolean(), nullable=False),
        sa.Column("verification_owner_id", sa.Uuid(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scheduled_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scheduled_finish", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "expected_avoided_cost",
            sa.Numeric(precision=38, scale=12),
            nullable=True,
        ),
        sa.Column(
            "expected_intervention_cost",
            sa.Numeric(precision=38, scale=12),
            nullable=True,
        ),
        sa.Column("currency_code", sa.String(length=3), nullable=True),
        sa.Column("confidence_score", sa.Numeric(precision=6, scale=5), nullable=True),
        sa.Column("limitations", PORTABLE_JSON, nullable=False),
        sa.Column("evidence_references", PORTABLE_JSON, nullable=False),
        sa.Column("idempotency_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(_status_check(), name="ck_operational_action_status"),
        sa.ForeignKeyConstraint(
            ["finding_id"],
            ["findings.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["forecast_execution_id"],
            ["forecast_executions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["orchestration_request_id"],
            ["intelligence_orchestration_requests.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reliability_execution_id"],
            ["reliability_executions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_fingerprint",
            name="uq_action_idempotency",
        ),
    )
    op.create_index(
        "ix_action_org_status",
        "operational_actions",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_action_org_source",
        "operational_actions",
        ["organization_id", "source_type", "source_reference"],
        unique=False,
    )
    op.create_index(
        "ix_action_org_due",
        "operational_actions",
        ["organization_id", "due_at"],
        unique=False,
    )

    op.create_table(
        "action_plan_steps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("action_id", sa.Uuid(), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=250), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("required_skill", sa.String(length=150), nullable=True),
        sa.Column("labor_category", sa.String(length=100), nullable=True),
        sa.Column(
            "estimated_labor_hours",
            sa.Numeric(precision=12, scale=4),
            nullable=True,
        ),
        sa.Column("required_tools", PORTABLE_JSON, nullable=False),
        sa.Column("required_permits", PORTABLE_JSON, nullable=False),
        sa.Column("work_order_reference", sa.String(length=255), nullable=True),
        sa.Column("external_system_reference", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["action_id"],
            ["operational_actions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "action_id",
            "sequence_number",
            name="uq_action_plan_step_sequence",
        ),
    )
    op.create_index(
        "ix_action_plan_step_org_action",
        "action_plan_steps",
        ["organization_id", "action_id"],
        unique=False,
    )

    op.create_table(
        "action_dependencies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("action_id", sa.Uuid(), nullable=False),
        sa.Column("prerequisite_action_id", sa.Uuid(), nullable=False),
        sa.Column("dependency_type", sa.String(length=50), nullable=False),
        sa.Column("mandatory", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("blocking_reason", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action_id <> prerequisite_action_id",
            name="ck_action_dependency_self",
        ),
        sa.ForeignKeyConstraint(
            ["action_id"],
            ["operational_actions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["prerequisite_action_id"],
            ["operational_actions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "action_id",
            "prerequisite_action_id",
            name="uq_action_dependency_pair",
        ),
    )
    op.create_index(
        "ix_action_dependency_org_action",
        "action_dependencies",
        ["organization_id", "action_id"],
        unique=False,
    )

    op.create_table(
        "action_resource_requirements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("action_id", sa.Uuid(), nullable=False),
        sa.Column("resource_type", sa.String(length=40), nullable=False),
        sa.Column("resource_identifier", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("required_quantity", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column(
            "available_quantity",
            sa.Numeric(precision=18, scale=6),
            nullable=True,
        ),
        sa.Column("mandatory", sa.Boolean(), nullable=False),
        sa.Column("inventory_check_status", sa.String(length=40), nullable=False),
        sa.Column("reservation_status", sa.String(length=40), nullable=False),
        sa.Column("reservation_reference", sa.String(length=255), nullable=True),
        sa.Column("source_system_reference", sa.String(length=255), nullable=True),
        sa.Column("required_by", sa.DateTime(timezone=True), nullable=True),
        sa.Column("shortage", sa.Boolean(), nullable=False),
        sa.Column("limitation", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["action_id"],
            ["operational_actions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_action_resource_org_action",
        "action_resource_requirements",
        ["organization_id", "action_id"],
        unique=False,
    )

    op.create_table(
        "action_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("action_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("prior_status", sa.String(length=40), nullable=True),
        sa.Column("new_status", sa.String(length=40), nullable=True),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("actor_role", sa.String(length=50), nullable=False),
        sa.Column("reason_code", sa.String(length=100), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("metadata_json", PORTABLE_JSON, nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["action_id"],
            ["operational_actions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "action_id",
            "idempotency_key",
            name="uq_action_event_idempotency",
        ),
    )
    op.create_index(
        "ix_action_event_org_action",
        "action_events",
        ["organization_id", "action_id"],
        unique=False,
    )

    op.create_table(
        "action_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("action_id", sa.Uuid(), nullable=False),
        sa.Column("lifecycle_stage", sa.String(length=40), nullable=False),
        sa.Column("evidence_type", sa.String(length=50), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("source_identifier", sa.String(length=255), nullable=False),
        sa.Column("document_reference", sa.String(length=500), nullable=True),
        sa.Column(
            "measurement_value",
            sa.Numeric(precision=38, scale=12),
            nullable=True,
        ),
        sa.Column("measurement_unit", sa.String(length=50), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("metadata_json", PORTABLE_JSON, nullable=False),
        sa.Column("integrity_fingerprint", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["action_id"],
            ["operational_actions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_action_evidence_org_action",
        "action_evidence",
        ["organization_id", "action_id"],
        unique=False,
    )

    op.create_table(
        "action_outcomes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("action_id", sa.Uuid(), nullable=False),
        sa.Column("outcome_type", sa.String(length=30), nullable=False),
        sa.Column("avoided_cost", sa.Numeric(precision=38, scale=12), nullable=True),
        sa.Column(
            "intervention_cost",
            sa.Numeric(precision=38, scale=12),
            nullable=True,
        ),
        sa.Column(
            "downtime_avoided",
            sa.Numeric(precision=38, scale=12),
            nullable=True,
        ),
        sa.Column(
            "production_preserved",
            sa.Numeric(precision=38, scale=12),
            nullable=True,
        ),
        sa.Column("risk_reduction", sa.Numeric(precision=8, scale=5), nullable=True),
        sa.Column("currency_code", sa.String(length=3), nullable=True),
        sa.Column("confidence_score", sa.Numeric(precision=6, scale=5), nullable=True),
        sa.Column("calculation_method", sa.String(length=100), nullable=False),
        sa.Column("verification_method", sa.String(length=100), nullable=True),
        sa.Column("verified_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assumptions", PORTABLE_JSON, nullable=False),
        sa.Column("limitations", PORTABLE_JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["action_id"],
            ["operational_actions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "action_id",
            "outcome_type",
            name="uq_action_outcome_type",
        ),
    )
    op.create_index(
        "ix_action_outcome_org_action",
        "action_outcomes",
        ["organization_id", "action_id"],
        unique=False,
    )

    op.create_table(
        "action_model_feedback",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("action_id", sa.Uuid(), nullable=False),
        sa.Column("reliability_execution_id", sa.Uuid(), nullable=False),
        sa.Column(
            "prediction_outcome_classification",
            sa.String(length=50),
            nullable=False,
        ),
        sa.Column("intervention_performed", sa.Boolean(), nullable=False),
        sa.Column("failure_occurred", sa.Boolean(), nullable=False),
        sa.Column("failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("risk_reduced", sa.Boolean(), nullable=True),
        sa.Column(
            "predicted_probability",
            sa.Numeric(precision=8, scale=6),
            nullable=True,
        ),
        sa.Column("predicted_horizon_days", sa.Integer(), nullable=True),
        sa.Column(
            "actual_time_to_event_days",
            sa.Numeric(precision=12, scale=4),
            nullable=True,
        ),
        sa.Column("recommendation_accepted", sa.Boolean(), nullable=False),
        sa.Column("recommendation_executed", sa.Boolean(), nullable=False),
        sa.Column("calibration_feedback", PORTABLE_JSON, nullable=False),
        sa.Column("human_review_status", sa.String(length=40), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["action_id"],
            ["operational_actions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reliability_execution_id"],
            ["reliability_executions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "action_id",
            "reliability_execution_id",
            name="uq_action_feedback",
        ),
    )
    op.create_index(
        "ix_action_feedback_org_action",
        "action_model_feedback",
        ["organization_id", "action_id"],
        unique=False,
    )


def downgrade() -> None:
    for table_name in reversed(ACTION_TABLES):
        op.drop_table(table_name)
