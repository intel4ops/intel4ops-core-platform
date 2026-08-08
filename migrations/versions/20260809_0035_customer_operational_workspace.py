"""Customer operational workspace.

Revision ID: 20260809_0035
Revises: 20260808_0034
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260809_0035"
down_revision: str | None = "20260808_0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("organizations") as batch_op:
        batch_op.add_column(sa.Column("sub_industry", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("employee_count_range", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("annual_revenue_range", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("operating_site_count", sa.Integer(), nullable=True))
        batch_op.create_check_constraint(
            "ck_organizations_operating_site_count_non_negative",
            "operating_site_count IS NULL OR operating_site_count >= 0",
        )

    op.create_table(
        "organization_objectives",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("objective_code", sa.String(length=60), nullable=False),
        sa.Column("selected_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("selected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "objective_code", name="uq_organization_objectives_org_code"
        ),
    )
    op.create_index(
        "ix_organization_objectives_org",
        "organization_objectives",
        ["organization_id"],
        unique=False,
    )

    op.create_table(
        "organization_challenges",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("challenge_code", sa.String(length=60), nullable=False),
        sa.Column("selected_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("selected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "challenge_code", name="uq_organization_challenges_org_code"
        ),
    )
    op.create_index(
        "ix_organization_challenges_org",
        "organization_challenges",
        ["organization_id"],
        unique=False,
    )

    op.create_table(
        "organization_systems",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("system_code", sa.String(length=60), nullable=False),
        sa.Column("custom_label", sa.String(length=150), nullable=True),
        sa.Column("selected_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("selected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "system_code",
            "custom_label",
            name="uq_organization_systems_org_code_label",
        ),
    )
    op.create_index(
        "ix_organization_systems_org", "organization_systems", ["organization_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_organization_systems_org", table_name="organization_systems")
    op.drop_table("organization_systems")

    op.drop_index("ix_organization_challenges_org", table_name="organization_challenges")
    op.drop_table("organization_challenges")

    op.drop_index("ix_organization_objectives_org", table_name="organization_objectives")
    op.drop_table("organization_objectives")

    with op.batch_alter_table("organizations") as batch_op:
        batch_op.drop_constraint(
            "ck_organizations_operating_site_count_non_negative", type_="check"
        )
        batch_op.drop_column("operating_site_count")
        batch_op.drop_column("annual_revenue_range")
        batch_op.drop_column("employee_count_range")
        batch_op.drop_column("sub_industry")
