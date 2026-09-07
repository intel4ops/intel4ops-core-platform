"""AGENTIC-CONTROL-001 Phase B/N: Agent Job domain model foundation

Revision ID: 20260906_0060
Revises: 20260903_0059
Create Date: 2026-09-06 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260906_0060"
down_revision: str | None = "20260903_0059"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RISK_CLASSES = ("R0", "R1", "R2", "R3")
_STATUSES = (
    "queued",
    "claimed",
    "running",
    "succeeded",
    "failed",
    "timed_out",
    "escalated",
    "owner_review_required",
    "cancelled",
)
_APPROVAL_STATUSES = ("not_required", "pending", "approved", "rejected")
_EVIDENCE_PLANES = ("production", "validation")
_EVENT_TYPES = (
    "CREATED",
    "ROUTED",
    "CLAIMED",
    "STARTED",
    "SUCCEEDED",
    "FAILED",
    "TIMED_OUT",
    "RETRIED",
    "ESCALATED",
    "OWNER_REVIEW_REQUIRED",
    "OWNER_APPROVED",
    "OWNER_REJECTED",
)

_JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    op.create_table(
        "agent_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("analysis_case_id", sa.Uuid(), nullable=True),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("simulation_id", sa.String(length=200), nullable=True),
        sa.Column("gap_id", sa.String(length=50), nullable=True),
        sa.Column("parent_job_id", sa.Uuid(), nullable=True),
        sa.Column("job_type", sa.String(length=100), nullable=False),
        sa.Column("risk_class", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("evidence_plane", sa.String(length=20), nullable=False),
        sa.Column("requested_capability", sa.String(length=150), nullable=False),
        sa.Column("assigned_worker", sa.String(length=200), nullable=True),
        sa.Column("assigned_model", sa.String(length=150), nullable=True),
        sa.Column("model_version", sa.String(length=50), nullable=True),
        sa.Column("prompt_template_version", sa.String(length=50), nullable=True),
        sa.Column("input_evidence_ref", sa.String(length=500), nullable=True),
        sa.Column("result_ref", sa.String(length=500), nullable=True),
        sa.Column("confidence", sa.Integer(), nullable=True),
        sa.Column("escalation_reason", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("execution_time_ms", sa.Integer(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("reasoning_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost", sa.Numeric(12, 6), nullable=True),
        sa.Column("actual_cost", sa.Numeric(12, 6), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_detail", sa.String(length=2000), nullable=True),
        sa.Column("owner_approval_required", sa.Boolean(), nullable=False),
        sa.Column("owner_approval_status", sa.String(length=20), nullable=False),
        sa.Column("execution_lease_id", sa.Uuid(), nullable=True),
        sa.Column("execution_worker_id", sa.String(length=200), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("client_idempotency_key", sa.String(length=200), nullable=True),
        sa.CheckConstraint(
            f"risk_class IN ({_quoted(_RISK_CLASSES)})", name="ck_agent_job_risk_class"
        ),
        sa.CheckConstraint(f"status IN ({_quoted(_STATUSES)})", name="ck_agent_job_status"),
        sa.CheckConstraint(
            f"owner_approval_status IN ({_quoted(_APPROVAL_STATUSES)})",
            name="ck_agent_job_owner_approval_status",
        ),
        sa.CheckConstraint(
            f"evidence_plane IN ({_quoted(_EVIDENCE_PLANES)})", name="ck_agent_job_evidence_plane"
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 100)",
            name="ck_agent_job_confidence_range",
        ),
        sa.CheckConstraint("retry_count >= 0", name="ck_agent_job_retry_count"),
        sa.CheckConstraint(
            "(owner_approval_required = false AND owner_approval_status = 'not_required') "
            "OR (owner_approval_required = true AND owner_approval_status != 'not_required')",
            name="ck_agent_job_owner_gate_consistency",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["parent_job_id"], ["agent_jobs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_job_dispatch_fifo", "agent_jobs", ["status", "risk_class", "created_at", "id"]
    )
    op.create_index("ix_agent_job_stale_heartbeat", "agent_jobs", ["status", "heartbeat_at"])
    op.create_index("ix_agent_job_org_created", "agent_jobs", ["organization_id", "created_at"])
    op.create_index("ix_agent_job_case", "agent_jobs", ["analysis_case_id"])
    op.create_index("ix_agent_job_run", "agent_jobs", ["run_id"])
    op.create_index("ix_agent_job_simulation", "agent_jobs", ["simulation_id"])
    op.create_index("ix_agent_job_gap", "agent_jobs", ["gap_id"])
    op.create_index("ix_agent_job_parent", "agent_jobs", ["parent_job_id"])
    op.create_index("ix_agent_job_owner_review", "agent_jobs", ["owner_approval_status"])

    op.create_table(
        "agent_job_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("agent_job_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=30), nullable=False),
        sa.Column("detail_json", _JSON, nullable=True),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"event_type IN ({_quoted(_EVENT_TYPES)})", name="ck_agent_job_event_type"
        ),
        sa.ForeignKeyConstraint(["agent_job_id"], ["agent_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_job_event_job", "agent_job_events", ["agent_job_id", "created_at"])
    op.create_index(
        "uq_agent_job_event_idempotency",
        "agent_job_events",
        ["agent_job_id", "event_type", "idempotency_key"],
        unique=True,
    )

    op.create_table(
        "agent_worker_credentials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("worker_id", sa.String(length=200), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("allowed_risk_classes", _JSON, nullable=False),
        sa.Column("allowed_job_types", _JSON, nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("worker_id", name="uq_agent_worker_credential_worker_id"),
    )
    op.create_index(
        "ix_agent_worker_credential_org", "agent_worker_credentials", ["organization_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_agent_worker_credential_org", table_name="agent_worker_credentials")
    op.drop_table("agent_worker_credentials")

    op.drop_index("uq_agent_job_event_idempotency", table_name="agent_job_events")
    op.drop_index("ix_agent_job_event_job", table_name="agent_job_events")
    op.drop_table("agent_job_events")

    op.drop_index("ix_agent_job_owner_review", table_name="agent_jobs")
    op.drop_index("ix_agent_job_parent", table_name="agent_jobs")
    op.drop_index("ix_agent_job_gap", table_name="agent_jobs")
    op.drop_index("ix_agent_job_simulation", table_name="agent_jobs")
    op.drop_index("ix_agent_job_run", table_name="agent_jobs")
    op.drop_index("ix_agent_job_case", table_name="agent_jobs")
    op.drop_index("ix_agent_job_org_created", table_name="agent_jobs")
    op.drop_index("ix_agent_job_stale_heartbeat", table_name="agent_jobs")
    op.drop_index("ix_agent_job_dispatch_fifo", table_name="agent_jobs")
    op.drop_table("agent_jobs")
