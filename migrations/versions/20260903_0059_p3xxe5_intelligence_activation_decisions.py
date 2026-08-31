"""P3.xxE.5 intelligence activation decisions (SHADOW mode)

Revision ID: 20260903_0059
Revises: 20260902_0058
Create Date: 2026-09-03 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260903_0059"
down_revision: str | None = "20260902_0058"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MODES = ("shadow", "governed")
_STATUSES = ("DISABLED", "READY", "PARTIAL", "BLOCKED")

_JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    op.create_table(
        "intelligence_activation_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_case_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("pack_code", sa.String(length=40), nullable=False),
        sa.Column("rule_code", sa.String(length=100), nullable=False),
        sa.Column("pack_version", sa.String(length=20), nullable=False),
        sa.Column("activation_policy_version", sa.String(length=20), nullable=False),
        sa.Column("mode", sa.String(length=10), nullable=False),
        sa.Column("legacy_activated", sa.Boolean(), nullable=False),
        sa.Column("legacy_reason", sa.String(length=500), nullable=False),
        sa.Column("governed_status", sa.String(length=10), nullable=False),
        sa.Column("governed_missing_summary", _JSON, nullable=False),
        sa.Column("governed_confidence_summary", _JSON, nullable=False),
        sa.Column("agree", sa.Boolean(), nullable=False),
        sa.Column("evidence_summary", _JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"mode IN ({_quoted(_MODES)})",
            name="ck_intelligence_activation_decision_mode",
        ),
        sa.CheckConstraint(
            f"governed_status IN ({_quoted(_STATUSES)})",
            name="ck_intelligence_activation_decision_status",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "analysis_case_id"],
            ["analysis_cases.organization_id", "analysis_cases.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["run_id"], ["analysis_case_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_intelligence_activation_decisions_org_case_run",
        "intelligence_activation_decisions",
        ["organization_id", "analysis_case_id", "run_id"],
        unique=False,
    )
    op.create_index(
        "ix_intelligence_activation_decisions_rule",
        "intelligence_activation_decisions",
        ["run_id", "rule_code"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_intelligence_activation_decisions_rule",
        table_name="intelligence_activation_decisions",
    )
    op.drop_index(
        "ix_intelligence_activation_decisions_org_case_run",
        table_name="intelligence_activation_decisions",
    )
    op.drop_table("intelligence_activation_decisions")
