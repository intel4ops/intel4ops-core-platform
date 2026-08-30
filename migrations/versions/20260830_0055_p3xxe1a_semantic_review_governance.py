"""P3.xxE.1A semantic review and governance foundation

Revision ID: 20260830_0055
Revises: 20260829_0054
Create Date: 2026-08-30 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260830_0055"
down_revision: str | None = "20260829_0054"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "semantic_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("decision_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("corrected_concept", sa.String(length=100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("reviewer_user_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_role", sa.String(length=50), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action IN ('confirm', 'correct', 'reject', 'mark_unresolved')",
            name="ck_semantic_review_action",
        ),
        sa.ForeignKeyConstraint(
            ["decision_id"], ["semantic_interpretation_decisions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_semantic_reviews_decision", "semantic_reviews", ["decision_id"], unique=False
    )
    op.create_index(
        "ix_semantic_reviews_org", "semantic_reviews", ["organization_id"], unique=False
    )

    op.create_table(
        "semantic_decision_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("decision_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("supersedes_version_id", sa.Uuid(), nullable=True),
        sa.Column("effective_status", sa.String(length=30), nullable=False),
        sa.Column("effective_concept", sa.String(length=100), nullable=True),
        sa.Column("review_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("effective_confidence", sa.Float(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(version_number = 1 AND supersedes_version_id IS NULL) OR "
            "(version_number > 1 AND supersedes_version_id IS NOT NULL)",
            name="ck_semantic_decision_versions_supersession",
        ),
        sa.CheckConstraint(
            "effective_status IN ('human_confirmed', 'human_corrected', 'human_rejected', "
            "'human_unresolved')",
            name="ck_semantic_decision_versions_status",
        ),
        sa.CheckConstraint(
            "source IN ('human_confirmation', 'human_correction', 'human_rejection', "
            "'human_unresolved')",
            name="ck_semantic_decision_versions_source",
        ),
        sa.ForeignKeyConstraint(
            ["decision_id"], ["semantic_interpretation_decisions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["review_id"], ["semantic_reviews.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["supersedes_version_id"], ["semantic_decision_versions.id"], ondelete="NO ACTION"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "decision_id",
            "version_number",
            name="uq_semantic_decision_versions_org_decision_version",
        ),
    )
    op.create_index(
        "ix_semantic_decision_versions_org_decision",
        "semantic_decision_versions",
        ["organization_id", "decision_id"],
        unique=False,
    )

    op.create_table(
        "semantic_decision_audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column("entity_type", sa.String(length=60), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("actor_type", sa.String(length=30), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column(
            "metadata_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_semantic_decision_audit_org_time",
        "semantic_decision_audit_events",
        ["organization_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_semantic_decision_audit_org_entity",
        "semantic_decision_audit_events",
        ["organization_id", "entity_type", "entity_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_semantic_decision_audit_org_entity", table_name="semantic_decision_audit_events"
    )
    op.drop_index(
        "ix_semantic_decision_audit_org_time", table_name="semantic_decision_audit_events"
    )
    op.drop_table("semantic_decision_audit_events")
    op.drop_index(
        "ix_semantic_decision_versions_org_decision", table_name="semantic_decision_versions"
    )
    op.drop_table("semantic_decision_versions")
    op.drop_index("ix_semantic_reviews_org", table_name="semantic_reviews")
    op.drop_index("ix_semantic_reviews_decision", table_name="semantic_reviews")
    op.drop_table("semantic_reviews")
