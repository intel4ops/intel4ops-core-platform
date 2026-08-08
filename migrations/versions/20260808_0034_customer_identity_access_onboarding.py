"""Customer identity, access and organization onboarding.

Revision ID: 20260808_0034
Revises: 20260807_0033
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

revision: str = "20260808_0034"
down_revision: str | None = "20260807_0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB_VARIANT = sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql")

MEMBERSHIP_ROLES = (
    "'platform_admin','organization_admin','analyst','operator','recovery_manager','viewer'"
)
INVITATION_STATUSES = "'pending','accepted','expired','revoked'"


def _assert_clean_membership_parent_keys() -> None:
    duplicates = op.get_bind().scalar(
        sa.text(
            """
            SELECT count(*)
            FROM (
                SELECT organization_id, id
                FROM organization_members
                GROUP BY organization_id, id
                HAVING count(*) > 1
            ) AS duplicate_targets
            """
        )
    )
    if duplicates:
        raise RuntimeError(
            f"uq_organization_members_org_id precondition failed with {duplicates} "
            "duplicate targets"
        )


def upgrade() -> None:
    offline = context.is_offline_mode()
    if not offline:
        _assert_clean_membership_parent_keys()

    with op.batch_alter_table("organization_members") as batch_op:
        batch_op.create_unique_constraint(
            "uq_organization_members_org_id",
            ["organization_id", "id"],
        )

    op.create_table(
        "access_audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column("entity_type", sa.String(length=60), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("metadata_json", JSONB_VARIANT, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_access_audit_org_time",
        "access_audit_events",
        ["organization_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_access_audit_org_entity",
        "access_audit_events",
        ["organization_id", "entity_type", "entity_id"],
        unique=False,
    )

    op.create_table(
        "organization_invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("invited_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("resulting_membership_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"role IN ({MEMBERSHIP_ROLES})",
            name="ck_organization_invitation_role",
        ),
        sa.CheckConstraint(
            f"status IN ({INVITATION_STATUSES})",
            name="ck_organization_invitation_status",
        ),
        sa.CheckConstraint(
            "status <> 'accepted' OR (accepted_at IS NOT NULL AND accepted_by_user_id IS NOT NULL "
            "AND resulting_membership_id IS NOT NULL)",
            name="ck_organization_invitation_acceptance",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id", "resulting_membership_id"],
            ["organization_members.organization_id", "organization_members.id"],
            name="fk_organization_invitations_org_membership",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_organization_invitations_org_id"),
        sa.UniqueConstraint("token_hash", name="uq_organization_invitations_token_hash"),
    )
    op.create_index(
        "ix_organization_invitations_org_status",
        "organization_invitations",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ux_organization_invitations_org_email_pending",
        "organization_invitations",
        ["organization_id", "email"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
        sqlite_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index(
        "ux_organization_invitations_org_email_pending",
        table_name="organization_invitations",
    )
    op.drop_index("ix_organization_invitations_org_status", table_name="organization_invitations")
    op.drop_table("organization_invitations")

    op.drop_index("ix_access_audit_org_entity", table_name="access_audit_events")
    op.drop_index("ix_access_audit_org_time", table_name="access_audit_events")
    op.drop_table("access_audit_events")

    with op.batch_alter_table("organization_members") as batch_op:
        batch_op.drop_constraint("uq_organization_members_org_id", type_="unique")
