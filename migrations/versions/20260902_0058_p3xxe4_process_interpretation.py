"""P3.xxE.4 operational process interpretation

Revision ID: 20260902_0058
Revises: 20260901_0057
Create Date: 2026-09-02 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260902_0058"
down_revision: str | None = "20260901_0057"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ENTITY_TYPES = (
    "ASSET",
    "WORK_ORDER",
    "CUSTOMER",
    "INVOICE",
    "PERSON",
    "PART",
    "LOCATION",
    "CONTRACT",
    "PRODUCT",
    "TRANSACTION",
    "EVENT",
    "OTHER",
)
_ACTIVITY_TYPES = (
    "CREATE",
    "SCHEDULE",
    "START",
    "PERFORM",
    "COMPLETE",
    "CLOSE",
    "CANCEL",
    "INVOICE",
    "PAY",
    "INSPECT",
    "APPROVE",
    "REJECT",
    "TRANSFER",
    "OTHER",
    "UNKNOWN",
    "GENERIC",
)
_BOUNDARY_STATUSES = ("LEFT_CENSORED", "RIGHT_CENSORED", "PARTIAL", "COMPLETE", "UNKNOWN")
_PROCESS_STATUSES = ("AUTO_ACCEPTED", "ACCEPTED_WITH_FLAG", "REVIEW_REQUIRED", "CONFLICTED")
_PROCESS_EDGE_TYPES = (
    "PRECEDES",
    "CONCURRENT",
    "OPTIONAL_BRANCH",
    "LOOP",
    "STATE_TRANSITION",
    "ORDER_UNRESOLVED",
)

_JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    op.create_table(
        "canonical_operational_processes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_case_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("anchor_entity_id", sa.Uuid(), nullable=True),
        sa.Column("anchor_entity_type", sa.String(length=40), nullable=True),
        sa.Column("anchor_confidence", sa.Float(), nullable=False),
        sa.Column("process_type", sa.String(length=60), nullable=True),
        sa.Column("process_label", sa.String(length=200), nullable=True),
        sa.Column("process_family", sa.String(length=60), nullable=True),
        sa.Column("process_family_confidence", sa.Float(), nullable=False),
        sa.Column("boundary_status", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("coverage_confidence", sa.Float(), nullable=False),
        sa.Column("activity_confidence", sa.Float(), nullable=False),
        sa.Column("entity_participation_confidence", sa.Float(), nullable=False),
        sa.Column("temporal_confidence", sa.Float(), nullable=False),
        sa.Column("precedence_consistency_confidence", sa.Float(), nullable=False),
        sa.Column("state_transition_confidence", sa.Float(), nullable=False),
        sa.Column("overall_confidence", sa.Float(), nullable=False),
        sa.Column("activity_count", sa.Integer(), nullable=False),
        sa.Column("edge_count", sa.Integer(), nullable=False),
        sa.Column("evidence_summary", _JSON, nullable=False),
        sa.Column("conflict_reason", sa.Text(), nullable=True),
        sa.Column("process_policy_version", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"anchor_entity_type IS NULL OR anchor_entity_type IN ({_quoted(_ENTITY_TYPES)})",
            name="ck_canonical_process_anchor_entity_type",
        ),
        sa.CheckConstraint(
            f"boundary_status IN ({_quoted(_BOUNDARY_STATUSES)})",
            name="ck_canonical_process_boundary_status",
        ),
        sa.CheckConstraint(
            f"status IN ({_quoted(_PROCESS_STATUSES)})",
            name="ck_canonical_process_status",
        ),
        sa.CheckConstraint(
            "anchor_confidence >= 0 AND anchor_confidence <= 1",
            name="ck_canonical_process_anchor_confidence_range",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "analysis_case_id"],
            ["analysis_cases.organization_id", "analysis_cases.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "anchor_entity_id"],
            ["canonical_case_entities.organization_id", "canonical_case_entities.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["run_id"], ["analysis_case_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_canonical_operational_processes_org_id"
        ),
    )
    op.create_index(
        "ix_canonical_operational_processes_org_case_run",
        "canonical_operational_processes",
        ["organization_id", "analysis_case_id", "run_id"],
        unique=False,
    )
    op.create_index(
        "ix_canonical_operational_processes_run_anchor_type",
        "canonical_operational_processes",
        ["run_id", "anchor_entity_type"],
        unique=False,
    )

    op.create_table(
        "canonical_process_activities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("process_id", sa.Uuid(), nullable=False),
        sa.Column("activity_type", sa.String(length=20), nullable=False),
        sa.Column("activity_label", sa.String(length=200), nullable=True),
        sa.Column("state_value", sa.String(length=100), nullable=True),
        sa.Column("primary_entity_id", sa.Uuid(), nullable=True),
        sa.Column("activity_type_confidence", sa.Float(), nullable=False),
        sa.Column("activity_existence_confidence", sa.Float(), nullable=False),
        sa.Column("temporal_confidence", sa.Float(), nullable=False),
        sa.Column("participation_confidence", sa.Float(), nullable=False),
        sa.Column("activity_confidence", sa.Float(), nullable=False),
        sa.Column("state_existence_confidence", sa.Float(), nullable=False),
        sa.Column("state_meaning_confidence", sa.Float(), nullable=False),
        sa.Column("temporal_evidence_tier", sa.String(length=10), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("occurred_at_precision", sa.String(length=20), nullable=False),
        sa.Column("timezone_source", sa.String(length=20), nullable=False),
        sa.Column("is_explicit_event", sa.Boolean(), nullable=False),
        sa.Column("corroboration_signals", _JSON, nullable=False),
        sa.Column("alternative_activity_types", _JSON, nullable=False),
        sa.Column("participation", _JSON, nullable=False),
        sa.Column("source_refs", _JSON, nullable=False),
        sa.Column("evidence_summary", _JSON, nullable=False),
        sa.Column("activity_policy_version", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"activity_type IN ({_quoted(_ACTIVITY_TYPES)})",
            name="ck_canonical_process_activity_type",
        ),
        sa.CheckConstraint(
            "activity_type_confidence >= 0 AND activity_type_confidence <= 1",
            name="ck_canonical_process_activity_type_confidence_range",
        ),
        sa.CheckConstraint(
            "activity_existence_confidence >= 0 AND activity_existence_confidence <= 1",
            name="ck_canonical_process_activity_existence_confidence_range",
        ),
        sa.CheckConstraint(
            "state_existence_confidence >= 0 AND state_existence_confidence <= 1",
            name="ck_canonical_process_activity_state_existence_confidence_range",
        ),
        sa.CheckConstraint(
            "state_meaning_confidence >= 0 AND state_meaning_confidence <= 1",
            name="ck_canonical_process_activity_state_meaning_confidence_range",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "process_id"],
            [
                "canonical_operational_processes.organization_id",
                "canonical_operational_processes.id",
            ],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "primary_entity_id"],
            ["canonical_case_entities.organization_id", "canonical_case_entities.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_canonical_process_activities_org_id"),
    )
    op.create_index(
        "ix_canonical_process_activities_process",
        "canonical_process_activities",
        ["process_id"],
        unique=False,
    )
    op.create_index(
        "ix_canonical_process_activities_primary_entity",
        "canonical_process_activities",
        ["primary_entity_id"],
        unique=False,
    )

    op.create_table(
        "canonical_process_edges",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("process_id", sa.Uuid(), nullable=False),
        sa.Column("from_activity_id", sa.Uuid(), nullable=False),
        sa.Column("to_activity_id", sa.Uuid(), nullable=False),
        sa.Column("edge_type", sa.String(length=20), nullable=False),
        sa.Column("from_state", sa.String(length=100), nullable=True),
        sa.Column("to_state", sa.String(length=100), nullable=True),
        sa.Column("support_count", sa.Integer(), nullable=False),
        sa.Column("a_before_b_count", sa.Integer(), nullable=False),
        sa.Column("b_before_a_count", sa.Integer(), nullable=False),
        sa.Column("same_time_count", sa.Integer(), nullable=False),
        sa.Column("unknown_order_count", sa.Integer(), nullable=False),
        sa.Column("observation_count", sa.Integer(), nullable=False),
        sa.Column("temporal_evidence_tier", sa.String(length=10), nullable=False),
        sa.Column("semantic_confidence", sa.Float(), nullable=False),
        sa.Column("entity_participation_confidence", sa.Float(), nullable=False),
        sa.Column("temporal_confidence", sa.Float(), nullable=False),
        sa.Column("repetition_confidence", sa.Float(), nullable=False),
        sa.Column("consistency_confidence", sa.Float(), nullable=False),
        sa.Column("conflict_penalty", sa.Float(), nullable=False),
        sa.Column("precedence_confidence", sa.Float(), nullable=False),
        sa.Column("contradiction_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("evidence_summary", _JSON, nullable=False),
        sa.Column("conflict_reason", sa.Text(), nullable=True),
        sa.Column("edge_policy_version", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "from_activity_id != to_activity_id", name="ck_canonical_process_edge_no_self"
        ),
        sa.CheckConstraint(
            f"edge_type IN ({_quoted(_PROCESS_EDGE_TYPES)})",
            name="ck_canonical_process_edge_type",
        ),
        sa.CheckConstraint(
            f"status IN ({_quoted(_PROCESS_STATUSES)})",
            name="ck_canonical_process_edge_status",
        ),
        sa.CheckConstraint(
            "precedence_confidence >= 0 AND precedence_confidence <= 1",
            name="ck_canonical_process_edge_precedence_confidence_range",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "process_id"],
            [
                "canonical_operational_processes.organization_id",
                "canonical_operational_processes.id",
            ],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "from_activity_id"],
            ["canonical_process_activities.organization_id", "canonical_process_activities.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "to_activity_id"],
            ["canonical_process_activities.organization_id", "canonical_process_activities.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_canonical_process_edges_process",
        "canonical_process_edges",
        ["process_id"],
        unique=False,
    )
    op.create_index(
        "ix_canonical_process_edges_from_to",
        "canonical_process_edges",
        ["from_activity_id", "to_activity_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_canonical_process_edges_from_to", table_name="canonical_process_edges")
    op.drop_index("ix_canonical_process_edges_process", table_name="canonical_process_edges")
    op.drop_table("canonical_process_edges")
    op.drop_index(
        "ix_canonical_process_activities_primary_entity",
        table_name="canonical_process_activities",
    )
    op.drop_index(
        "ix_canonical_process_activities_process", table_name="canonical_process_activities"
    )
    op.drop_table("canonical_process_activities")
    op.drop_index(
        "ix_canonical_operational_processes_run_anchor_type",
        table_name="canonical_operational_processes",
    )
    op.drop_index(
        "ix_canonical_operational_processes_org_case_run",
        table_name="canonical_operational_processes",
    )
    op.drop_table("canonical_operational_processes")
