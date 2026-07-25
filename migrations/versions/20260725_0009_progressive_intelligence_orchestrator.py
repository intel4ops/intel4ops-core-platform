"""Progressive Intelligence Orchestrator.

Revision ID: 20260725_0009
Revises: 20260725_0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260725_0009"
down_revision: str | None = "20260725_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

portable_json = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "intelligence_orchestration_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("request_code", sa.String(length=40), nullable=False),
        sa.Column("correlation_id", sa.String(length=100), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("definition_code", sa.String(length=100), nullable=False),
        sa.Column("definition_version", sa.String(length=30), nullable=False),
        sa.Column("requested_analytical_level", sa.String(length=40), nullable=True),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_version_id", sa.Uuid(), nullable=True),
        sa.Column("dataset_reference", sa.String(length=255), nullable=False),
        sa.Column("trust_assessment_id", sa.Uuid(), nullable=False),
        sa.Column("analytical_readiness_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("publish_finding", sa.Boolean(), nullable=False),
        sa.Column("parameters_summary", portable_json, nullable=False),
        sa.Column("request_context", portable_json, nullable=False),
        sa.Column("context_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("warnings", portable_json, nullable=False),
        sa.Column("limitations", portable_json, nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('received', 'validating', 'deciding', 'executing', "
            "'completed', 'completed_with_limitations', 'partially_completed', "
            "'blocked', 'failed', 'unsupported', 'cancelled')",
            name="ck_orchestration_request_status",
        ),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"], ["dataset_versions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["trust_assessment_id"], ["trust_assessments.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["analytical_readiness_id"],
            ["analytical_readiness_decisions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_code"),
        sa.UniqueConstraint(
            "organization_id",
            "correlation_id",
            name="uq_orchestration_requests_organization_correlation",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_orchestration_requests_organization_idempotency",
        ),
    )
    for name, columns in (
        (
            "ix_orchestration_requests_organization_status",
            ["organization_id", "status"],
        ),
        (
            "ix_orchestration_requests_organization_definition",
            ["organization_id", "definition_code", "definition_version"],
        ),
        (
            "ix_orchestration_requests_organization_requested",
            ["organization_id", "requested_at"],
        ),
        ("ix_orchestration_requests_dataset_id", ["dataset_id"]),
        (
            "ix_orchestration_requests_trust_assessment_id",
            ["trust_assessment_id"],
        ),
        ("ix_orchestration_requests_readiness_id", ["analytical_readiness_id"]),
    ):
        op.create_index(name, "intelligence_orchestration_requests", columns)

    op.create_table(
        "intelligence_orchestration_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("orchestration_request_id", sa.Uuid(), nullable=False),
        sa.Column("decision_sequence", sa.Integer(), nullable=False),
        sa.Column("definition_code", sa.String(length=100), nullable=False),
        sa.Column("definition_version", sa.String(length=30), nullable=False),
        sa.Column("requested_level", sa.String(length=40), nullable=True),
        sa.Column("selected_level", sa.String(length=40), nullable=True),
        sa.Column("selected_engine_code", sa.String(length=100), nullable=True),
        sa.Column("selected_engine_version", sa.String(length=30), nullable=True),
        sa.Column("alternatives_considered", portable_json, nullable=False),
        sa.Column("trust_status", sa.String(length=40), nullable=False),
        sa.Column("readiness_status", sa.String(length=40), nullable=False),
        sa.Column("sufficiency_status", sa.String(length=40), nullable=False),
        sa.Column("escalation_status", sa.String(length=40), nullable=False),
        sa.Column("decision", sa.String(length=40), nullable=False),
        sa.Column("decision_reason_code", sa.String(length=100), nullable=False),
        sa.Column("decision_summary", sa.Text(), nullable=False),
        sa.Column("policy_code", sa.String(length=100), nullable=False),
        sa.Column("policy_version", sa.String(length=30), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "decision IN ('execute', 'execute_with_warnings', "
            "'return_existing_result', 'block', 'defer', 'unsupported', "
            "'escalate', 'stop_with_current_result')",
            name="ck_orchestration_decision_type",
        ),
        sa.ForeignKeyConstraint(
            ["orchestration_request_id"],
            ["intelligence_orchestration_requests.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "orchestration_request_id",
            "decision_sequence",
            name="uq_orchestration_decision_sequence",
        ),
    )
    op.create_index(
        "ix_orchestration_decisions_organization_request",
        "intelligence_orchestration_decisions",
        ["organization_id", "orchestration_request_id"],
    )
    op.create_index(
        "ix_orchestration_decisions_selected_engine",
        "intelligence_orchestration_decisions",
        ["selected_engine_code"],
    )

    op.create_table(
        "intelligence_engine_registrations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("engine_code", sa.String(length=100), nullable=False),
        sa.Column("engine_name", sa.String(length=200), nullable=False),
        sa.Column("engine_version", sa.String(length=30), nullable=False),
        sa.Column("analytical_level", sa.String(length=40), nullable=False),
        sa.Column("capability_code", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("is_available", sa.Boolean(), nullable=False),
        sa.Column("supports_sync", sa.Boolean(), nullable=False),
        sa.Column("supports_async", sa.Boolean(), nullable=False),
        sa.Column("input_contract_version", sa.String(length=30), nullable=False),
        sa.Column("output_contract_version", sa.String(length=30), nullable=False),
        sa.Column("implementation_reference", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'inactive', 'deprecated', 'unavailable', 'experimental')",
            name="ck_engine_registration_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "engine_code",
            "engine_version",
            name="uq_engine_registration_code_version",
        ),
    )
    op.create_index(
        "ix_engine_registrations_level",
        "intelligence_engine_registrations",
        ["analytical_level"],
    )
    op.create_index(
        "ix_engine_registrations_capability",
        "intelligence_engine_registrations",
        ["capability_code"],
    )
    op.create_index(
        "ix_engine_registrations_available",
        "intelligence_engine_registrations",
        ["is_available"],
    )

    op.create_table(
        "intelligence_orchestration_steps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("orchestration_request_id", sa.Uuid(), nullable=False),
        sa.Column("step_sequence", sa.Integer(), nullable=False),
        sa.Column("analytical_level", sa.String(length=40), nullable=True),
        sa.Column("engine_code", sa.String(length=100), nullable=True),
        sa.Column("engine_version", sa.String(length=30), nullable=True),
        sa.Column("step_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_execution_id", sa.Uuid(), nullable=True),
        sa.Column("source_result_id", sa.Uuid(), nullable=True),
        sa.Column("finding_id", sa.Uuid(), nullable=True),
        sa.Column("input_reference_summary", portable_json, nullable=False),
        sa.Column("output_reference_summary", portable_json, nullable=False),
        sa.Column("warnings", portable_json, nullable=False),
        sa.Column("limitations", portable_json, nullable=False),
        sa.Column("block_reason_code", sa.String(length=100), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'completed', 'blocked', 'failed', 'skipped')",
            name="ck_orchestration_step_status",
        ),
        sa.CheckConstraint("step_sequence > 0", name="ck_orchestration_step_sequence"),
        sa.ForeignKeyConstraint(["finding_id"], ["findings.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["orchestration_request_id"],
            ["intelligence_orchestration_requests.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["source_execution_id"],
            ["intelligence_executions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_result_id"],
            ["intelligence_executions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "orchestration_request_id",
            "step_sequence",
            name="uq_orchestration_step_sequence",
        ),
    )
    op.create_index(
        "ix_orchestration_steps_organization_request",
        "intelligence_orchestration_steps",
        ["organization_id", "orchestration_request_id"],
    )
    op.create_index(
        "ix_orchestration_steps_execution",
        "intelligence_orchestration_steps",
        ["organization_id", "source_execution_id"],
    )
    op.create_index(
        "ix_orchestration_steps_finding_id",
        "intelligence_orchestration_steps",
        ["finding_id"],
    )

    op.create_table(
        "intelligence_orchestration_status_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("orchestration_request_id", sa.Uuid(), nullable=False),
        sa.Column("transition_sequence", sa.Integer(), nullable=False),
        sa.Column("previous_status", sa.String(length=40), nullable=True),
        sa.Column("new_status", sa.String(length=40), nullable=False),
        sa.Column("reason_code", sa.String(length=100), nullable=False),
        sa.Column("changed_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata_json", portable_json, nullable=False),
        sa.CheckConstraint(
            "transition_sequence > 0",
            name="ck_orchestration_history_sequence",
        ),
        sa.ForeignKeyConstraint(
            ["orchestration_request_id"],
            ["intelligence_orchestration_requests.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "orchestration_request_id",
            "transition_sequence",
            name="uq_orchestration_history_sequence",
        ),
    )
    op.create_index(
        "ix_orchestration_history_organization_request",
        "intelligence_orchestration_status_history",
        ["organization_id", "orchestration_request_id"],
    )
    op.create_index(
        "ix_orchestration_history_changed_at",
        "intelligence_orchestration_status_history",
        ["changed_at"],
    )


def downgrade() -> None:
    for table, indexes in (
        (
            "intelligence_orchestration_status_history",
            (
                "ix_orchestration_history_changed_at",
                "ix_orchestration_history_organization_request",
            ),
        ),
        (
            "intelligence_orchestration_steps",
            (
                "ix_orchestration_steps_finding_id",
                "ix_orchestration_steps_execution",
                "ix_orchestration_steps_organization_request",
            ),
        ),
        (
            "intelligence_engine_registrations",
            (
                "ix_engine_registrations_available",
                "ix_engine_registrations_capability",
                "ix_engine_registrations_level",
            ),
        ),
        (
            "intelligence_orchestration_decisions",
            (
                "ix_orchestration_decisions_selected_engine",
                "ix_orchestration_decisions_organization_request",
            ),
        ),
        (
            "intelligence_orchestration_requests",
            (
                "ix_orchestration_requests_readiness_id",
                "ix_orchestration_requests_trust_assessment_id",
                "ix_orchestration_requests_dataset_id",
                "ix_orchestration_requests_organization_requested",
                "ix_orchestration_requests_organization_definition",
                "ix_orchestration_requests_organization_status",
            ),
        ),
    ):
        for index in indexes:
            op.drop_index(index, table_name=table)
        op.drop_table(table)
