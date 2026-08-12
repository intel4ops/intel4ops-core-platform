"""Add explicit governance tier to findings.

Revision ID: 20260816_0042
Revises: 20260815_0041
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

revision: str = "20260816_0042"
down_revision: str | None = "20260815_0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GOVERNED = "GOVERNED"
LIGHTWEIGHT = "LIGHTWEIGHT"


def _backfill_governance_tier() -> None:
    if context.is_offline_mode():
        return
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE findings SET governance_tier = :governed "
            "WHERE governance_tier IS NULL "
            "AND source_execution_id IS NOT NULL "
            "AND trust_assessment_id IS NOT NULL "
            "AND analytical_readiness_id IS NOT NULL "
            "AND dataset_id IS NOT NULL"
        ),
        {"governed": GOVERNED},
    )
    bind.execute(
        sa.text("UPDATE findings SET governance_tier = :lightweight WHERE governance_tier IS NULL"),
        {"lightweight": LIGHTWEIGHT},
    )


def _validate_backfill() -> None:
    if context.is_offline_mode():
        return
    bind = op.get_bind()
    remaining = bind.execute(
        sa.text("SELECT COUNT(*) FROM findings WHERE governance_tier IS NULL")
    ).scalar_one()
    if remaining:
        raise RuntimeError(
            f"Cannot enforce findings.governance_tier NOT NULL: "
            f"{remaining} row(s) remain unclassified"
        )


def upgrade() -> None:
    with op.batch_alter_table("findings") as batch:
        batch.add_column(sa.Column("governance_tier", sa.String(length=20), nullable=True))

    _backfill_governance_tier()
    _validate_backfill()

    with op.batch_alter_table("findings") as batch:
        batch.alter_column(
            "governance_tier",
            existing_type=sa.String(length=20),
            nullable=False,
        )
        batch.create_check_constraint(
            "ck_findings_governance_tier",
            "governance_tier IN ('GOVERNED', 'LIGHTWEIGHT')",
        )
        batch.create_index(
            "ix_findings_organization_governance_tier",
            ["organization_id", "governance_tier"],
        )


def downgrade() -> None:
    with op.batch_alter_table("findings") as batch:
        batch.drop_index("ix_findings_organization_governance_tier")
        batch.drop_constraint("ck_findings_governance_tier", type_="check")
        batch.drop_column("governance_tier")
