"""P3.xxE.1 semantic foundation

Revision ID: 20260829_0054
Revises: 20260828_0054
Create Date: 2026-08-29 11:27:28.128864
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260829_0054"
down_revision: str | None = "20260828_0054"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "semantic_dataset_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_case_dataset_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_label", sa.String(length=255), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("column_count", sa.Integer(), nullable=False),
        sa.Column(
            "field_profiles",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["analysis_case_dataset_id"], ["analysis_case_datasets.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["run_id"], ["analysis_case_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_semantic_dataset_profiles_dataset",
        "semantic_dataset_profiles",
        ["analysis_case_dataset_id"],
        unique=False,
    )
    op.create_index(
        "ix_semantic_dataset_profiles_run",
        "semantic_dataset_profiles",
        ["run_id"],
        unique=False,
    )
    op.create_table(
        "semantic_interpretation_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_case_dataset_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("source_field", sa.String(length=255), nullable=False),
        sa.Column("selected_concept", sa.String(length=100), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column(
            "evidence_summary",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "alternative_candidates",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("decision_source", sa.String(length=100), nullable=False),
        sa.Column("decision_version", sa.String(length=100), nullable=False),
        sa.Column("review_actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("review_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('auto_accepted', 'accepted_with_flag', 'review_required', "
            "'unresolved', 'human_confirmed', 'human_rejected')",
            name="ck_semantic_interpretation_decision_status",
        ),
        sa.ForeignKeyConstraint(
            ["analysis_case_dataset_id"], ["analysis_case_datasets.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["run_id"], ["analysis_case_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_semantic_interpretation_decisions_dataset",
        "semantic_interpretation_decisions",
        ["analysis_case_dataset_id"],
        unique=False,
    )
    op.create_index(
        "ix_semantic_interpretation_decisions_run",
        "semantic_interpretation_decisions",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        "ix_semantic_interpretation_decisions_status",
        "semantic_interpretation_decisions",
        ["status"],
        unique=False,
    )
    op.create_table(
        "semantic_role_interpretations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_case_dataset_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("primary_role", sa.String(length=50), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "evidence",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "secondary_roles",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "alternative_roles",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["analysis_case_dataset_id"], ["analysis_case_datasets.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["run_id"], ["analysis_case_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_semantic_role_interpretations_dataset",
        "semantic_role_interpretations",
        ["analysis_case_dataset_id"],
        unique=False,
    )
    op.create_index(
        "ix_semantic_role_interpretations_run",
        "semantic_role_interpretations",
        ["run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_semantic_role_interpretations_run", table_name="semantic_role_interpretations"
    )
    op.drop_index(
        "ix_semantic_role_interpretations_dataset", table_name="semantic_role_interpretations"
    )
    op.drop_table("semantic_role_interpretations")
    op.drop_index(
        "ix_semantic_interpretation_decisions_status",
        table_name="semantic_interpretation_decisions",
    )
    op.drop_index(
        "ix_semantic_interpretation_decisions_run", table_name="semantic_interpretation_decisions"
    )
    op.drop_index(
        "ix_semantic_interpretation_decisions_dataset",
        table_name="semantic_interpretation_decisions",
    )
    op.drop_table("semantic_interpretation_decisions")
    op.drop_index("ix_semantic_dataset_profiles_run", table_name="semantic_dataset_profiles")
    op.drop_index("ix_semantic_dataset_profiles_dataset", table_name="semantic_dataset_profiles")
    op.drop_table("semantic_dataset_profiles")
