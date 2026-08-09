"""Add governed AI operational profile persistence.

Revision ID: 20260811_0037
Revises: 20260810_0036
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260811_0037"
down_revision: str | None = "20260810_0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

portable_json = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "ai_operational_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("provider_code", sa.String(length=60), nullable=False),
        sa.Column("model_code", sa.String(length=150), nullable=False),
        sa.Column("model_version", sa.String(length=150), nullable=True),
        sa.Column("template_code", sa.String(length=100), nullable=False),
        sa.Column("template_version", sa.String(length=30), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("execution_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("response_hash", sa.String(length=64), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("profile_summary_snapshot", portable_json, nullable=False),
        sa.Column("input_provenance_snapshot", portable_json, nullable=False),
        sa.Column("observability_snapshot", portable_json, nullable=False),
        sa.Column("limitations", portable_json, nullable=False),
        sa.Column("failure_code", sa.String(length=100), nullable=True),
        sa.Column("failure_message_sanitized", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('running','completed','partial','failed','unavailable')",
            name="ck_ai_operational_profiles_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_ai_operational_profiles_org_id"),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_ai_operational_profiles_org_idempotency",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "execution_fingerprint",
            name="uq_ai_operational_profiles_org_execution_fingerprint",
        ),
    )
    op.create_index(
        "ix_ai_operational_profiles_org_generated",
        "ai_operational_profiles",
        ["organization_id", "generated_at"],
        unique=False,
    )
    op.create_index(
        "ix_ai_operational_profiles_org_status",
        "ai_operational_profiles",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_table(
        "ai_profile_inferences",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("inference_type", sa.String(length=60), nullable=False),
        sa.Column("proposed_code", sa.String(length=150), nullable=True),
        sa.Column("proposed_value", sa.String(length=500), nullable=True),
        sa.Column("display_value", sa.String(length=500), nullable=True),
        sa.Column("confidence", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("reasoning_summary", sa.String(length=500), nullable=False),
        sa.Column("evidence_references", portable_json, nullable=False),
        sa.Column("alternative_candidates", portable_json, nullable=False),
        sa.Column("provider_metadata", portable_json, nullable=False),
        sa.Column("confirmed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deferred_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("deferred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("corrected_code", sa.String(length=150), nullable=True),
        sa.Column("corrected_value", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "confidence IN ('HIGH','MEDIUM','LOW')",
            name="ck_ai_profile_inferences_confidence",
        ),
        sa.CheckConstraint(
            "status IN ('INFERRED','CONFIRMED','CORRECTED','REJECTED','DEFERRED','SUPERSEDED')",
            name="ck_ai_profile_inferences_status",
        ),
        sa.CheckConstraint("sequence_number > 0", name="ck_ai_profile_inferences_sequence"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["organization_id", "profile_id"],
            ["ai_operational_profiles.organization_id", "ai_operational_profiles.id"],
            name="fk_ai_profile_inferences_org_profile",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_ai_profile_inferences_org_id"),
        sa.UniqueConstraint(
            "profile_id",
            "sequence_number",
            name="uq_ai_profile_inferences_profile_sequence",
        ),
    )
    op.create_index(
        "ix_ai_profile_inferences_org_profile",
        "ai_profile_inferences",
        ["organization_id", "profile_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_profile_inferences_org_status",
        "ai_profile_inferences",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_ai_profile_inferences_org_type",
        "ai_profile_inferences",
        ["organization_id", "inference_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ai_profile_inferences_org_type", table_name="ai_profile_inferences")
    op.drop_index("ix_ai_profile_inferences_org_status", table_name="ai_profile_inferences")
    op.drop_index("ix_ai_profile_inferences_org_profile", table_name="ai_profile_inferences")
    op.drop_table("ai_profile_inferences")
    op.drop_index("ix_ai_operational_profiles_org_status", table_name="ai_operational_profiles")
    op.drop_index("ix_ai_operational_profiles_org_generated", table_name="ai_operational_profiles")
    op.drop_table("ai_operational_profiles")
