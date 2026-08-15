"""Add governed versioned Knowledge Packs.

Revision ID: 20260820_0046
Revises: 20260819_0045
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260820_0046"
down_revision: str | None = "20260819_0045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
portable_json = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "knowledge_packs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(250), nullable=False),
        sa.Column("slug", sa.String(150), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("industry", sa.String(100), nullable=False),
        sa.Column("domain", sa.String(100), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "id", name="uq_knowledge_pack_org_id"),
        sa.UniqueConstraint("organization_id", "slug", name="uq_knowledge_pack_org_slug"),
    )
    op.create_index(
        "ix_knowledge_pack_org_domain", "knowledge_packs", ["organization_id", "domain", "industry"]
    )
    op.create_table(
        "knowledge_pack_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("knowledge_pack_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("lifecycle_status", sa.String(20), nullable=False),
        sa.Column("change_summary", sa.Text(), nullable=False),
        sa.Column("provenance_summary", sa.String(20), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("reviewed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("approved_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("organization_id", "id", name="uq_knowledge_pack_version_org_id"),
        sa.UniqueConstraint("knowledge_pack_id", "version_number", name="uq_pack_version_number"),
        sa.ForeignKeyConstraint(
            ["organization_id", "knowledge_pack_id"],
            ["knowledge_packs.organization_id", "knowledge_packs.id"],
            name="fk_pack_version_org_pack",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("version_number > 0", name="ck_pack_version_positive"),
        sa.CheckConstraint(
            "lifecycle_status IN "
            "('draft','in_review','approved','rejected','superseded','retired')",
            name="ck_pack_version_status",
        ),
        sa.CheckConstraint(
            "provenance_summary IS NULL OR provenance_summary IN "
            "('production','simulation','manual','mixed')",
            name="ck_pack_version_provenance",
        ),
    )
    op.create_index(
        "ix_pack_version_org_pack_status",
        "knowledge_pack_versions",
        ["organization_id", "knowledge_pack_id", "lifecycle_status"],
    )
    op.create_table(
        "knowledge_pack_learning_links",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("knowledge_pack_version_id", sa.Uuid(), nullable=False),
        sa.Column("operational_learning_id", sa.Uuid(), nullable=False),
        sa.Column("inclusion_rationale", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "knowledge_pack_version_id",
            "operational_learning_id",
            name="uq_pack_version_learning",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "knowledge_pack_version_id"],
            ["knowledge_pack_versions.organization_id", "knowledge_pack_versions.id"],
            name="fk_pack_learning_org_version",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "operational_learning_id"],
            ["operational_learnings.organization_id", "operational_learnings.id"],
            name="fk_pack_learning_org_learning",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_pack_learning_org_version",
        "knowledge_pack_learning_links",
        ["organization_id", "knowledge_pack_version_id"],
    )
    op.create_table(
        "knowledge_pack_audit_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("knowledge_pack_id", sa.Uuid(), nullable=False),
        sa.Column(
            "knowledge_pack_version_id",
            sa.Uuid(),
            sa.ForeignKey("knowledge_pack_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("prior_status", sa.String(20), nullable=True),
        sa.Column("new_status", sa.String(20), nullable=True),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("actor_role", sa.String(50), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("metadata_json", portable_json, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "knowledge_pack_id"],
            ["knowledge_packs.organization_id", "knowledge_packs.id"],
            name="fk_pack_audit_org_pack",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_pack_audit_org_pack_time",
        "knowledge_pack_audit_events",
        ["organization_id", "knowledge_pack_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_table("knowledge_pack_audit_events")
    op.drop_table("knowledge_pack_learning_links")
    op.drop_table("knowledge_pack_versions")
    op.drop_table("knowledge_packs")
