"""Add immutable directional value scan projections.

Revision ID: 20260810_0036
Revises: 20260809_0035
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260810_0036"
down_revision: str | None = "20260809_0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

portable_json = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "directional_value_scans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("ranking_policy_code", sa.String(length=100), nullable=False),
        sa.Column("ranking_policy_version", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("candidate_finding_count", sa.Integer(), nullable=False),
        sa.Column("opportunity_count", sa.Integer(), nullable=False),
        sa.Column("data_gap_count", sa.Integer(), nullable=False),
        sa.Column("data_coverage_snapshot", portable_json, nullable=False),
        sa.Column("trust_readiness_snapshot", portable_json, nullable=False),
        sa.Column("customer_context_snapshot", portable_json, nullable=False),
        sa.Column("opportunity_snapshot", portable_json, nullable=False),
        sa.Column("data_gap_snapshot", portable_json, nullable=False),
        sa.Column("next_investigation_snapshot", portable_json, nullable=True),
        sa.Column("provenance_snapshot", portable_json, nullable=False),
        sa.Column("limitations", portable_json, nullable=False),
        sa.Column("result_content_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('completed', 'partial', 'refused')",
            name="ck_directional_value_scans_status",
        ),
        sa.CheckConstraint(
            "candidate_finding_count >= 0",
            name="ck_directional_value_scans_candidate_count_non_negative",
        ),
        sa.CheckConstraint(
            "opportunity_count >= 0",
            name="ck_directional_value_scans_opportunity_count_non_negative",
        ),
        sa.CheckConstraint(
            "data_gap_count >= 0",
            name="ck_directional_value_scans_data_gap_count_non_negative",
        ),
        sa.CheckConstraint(
            "opportunity_count <= candidate_finding_count",
            name="ck_directional_value_scans_opportunity_within_candidates",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_directional_value_scans_org_id"),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_directional_value_scans_org_idempotency",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "input_fingerprint",
            name="uq_directional_value_scans_org_input_fingerprint",
        ),
    )
    op.create_index(
        "ix_directional_value_scans_org_generated_at",
        "directional_value_scans",
        ["organization_id", "generated_at"],
        unique=False,
    )
    op.create_index(
        "ix_directional_value_scans_org_status",
        "directional_value_scans",
        ["organization_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_directional_value_scans_org_status",
        table_name="directional_value_scans",
    )
    op.drop_index(
        "ix_directional_value_scans_org_generated_at",
        table_name="directional_value_scans",
    )
    op.drop_table("directional_value_scans")
