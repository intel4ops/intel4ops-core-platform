"""Add immutable grounded executive narratives.

Revision ID: 20260812_0038
Revises: 20260811_0037
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260812_0038"
down_revision: str | None = "20260811_0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

portable_json = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "grounded_executive_narratives",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("scan_id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=True),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("audience", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("provider_code", sa.String(length=60), nullable=True),
        sa.Column("model_code", sa.String(length=150), nullable=True),
        sa.Column("model_version", sa.String(length=150), nullable=True),
        sa.Column("template_code", sa.String(length=100), nullable=False),
        sa.Column("template_version", sa.String(length=30), nullable=False),
        sa.Column("schema_version", sa.String(length=30), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("execution_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("source_scan_content_hash", sa.String(length=64), nullable=False),
        sa.Column("source_profile_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("structured_source_snapshot", portable_json, nullable=False),
        sa.Column("structured_narrative_snapshot", portable_json, nullable=False),
        sa.Column("limitations", portable_json, nullable=False),
        sa.Column("observability_snapshot", portable_json, nullable=False),
        sa.Column("provider_failure_code", sa.String(length=100), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("audience = 'EXECUTIVE'", name="ck_grounded_narratives_audience"),
        sa.CheckConstraint(
            "status IN ('completed','fallback')", name="ck_grounded_narratives_status"
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["organization_id", "scan_id"],
            ["directional_value_scans.organization_id", "directional_value_scans.id"],
            name="fk_grounded_narratives_org_scan",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "profile_id"],
            ["ai_operational_profiles.organization_id", "ai_operational_profiles.id"],
            name="fk_grounded_narratives_org_profile",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_grounded_narratives_org_id"),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_grounded_narratives_org_idempotency",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "execution_fingerprint",
            name="uq_grounded_narratives_org_execution_fingerprint",
        ),
    )
    op.create_index(
        "ix_grounded_narratives_org_generated",
        "grounded_executive_narratives",
        ["organization_id", "generated_at"],
        unique=False,
    )
    op.create_index(
        "ix_grounded_narratives_org_scan",
        "grounded_executive_narratives",
        ["organization_id", "scan_id"],
        unique=False,
    )
    op.create_index(
        "ix_grounded_narratives_org_profile",
        "grounded_executive_narratives",
        ["organization_id", "profile_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_grounded_narratives_org_profile", table_name="grounded_executive_narratives")
    op.drop_index("ix_grounded_narratives_org_scan", table_name="grounded_executive_narratives")
    op.drop_index(
        "ix_grounded_narratives_org_generated", table_name="grounded_executive_narratives"
    )
    op.drop_table("grounded_executive_narratives")
