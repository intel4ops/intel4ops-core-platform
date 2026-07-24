"""Create organization membership and authorization foundation.

Revision ID: 20260724_0002
Revises: 20260724_0001
Create Date: 2026-07-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260724_0002"
down_revision: str | None = "20260724_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organization_members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("invited_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "role IN ('platform_admin', 'organization_admin', 'analyst', 'operator', "
            "'recovery_manager', 'viewer')",
            name="ck_organization_members_role",
        ),
        sa.CheckConstraint(
            "status IN ('invited', 'active', 'suspended', 'revoked')",
            name="ck_organization_members_status",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_organization_members_organization_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "user_id",
            name="uq_organization_members_organization_user",
        ),
    )
    op.create_index(
        "ix_organization_members_organization_id",
        "organization_members",
        ["organization_id"],
    )
    op.create_index(
        "ix_organization_members_user_id",
        "organization_members",
        ["user_id"],
    )
    op.create_index(
        "ix_organization_members_role",
        "organization_members",
        ["role"],
    )
    op.create_index(
        "ix_organization_members_status",
        "organization_members",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_organization_members_status", table_name="organization_members")
    op.drop_index("ix_organization_members_role", table_name="organization_members")
    op.drop_index("ix_organization_members_user_id", table_name="organization_members")
    op.drop_index(
        "ix_organization_members_organization_id",
        table_name="organization_members",
    )
    op.drop_table("organization_members")
