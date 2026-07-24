"""Create organizations and tenant-scoped operational tables.

Revision ID: 20260724_0001
Revises:
Create Date: 2026-07-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260724_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("legal_name", sa.String(length=250), nullable=True),
        sa.Column("industry", sa.String(length=100), nullable=True),
        sa.Column("country_code", sa.String(length=2), nullable=False),
        sa.Column("default_currency", sa.String(length=3), nullable=False),
        sa.Column("timezone", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_organizations_slug"), "organizations", ["slug"], unique=True)

    op.create_table(
        "findings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("rule_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(length=250), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("domain", sa.String(length=100), nullable=False),
        sa.Column("severity", sa.String(length=50), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("exposure_low", sa.Float(), nullable=False),
        sa.Column("exposure_high", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("ontology_concept_ids", sa.JSON(), nullable=False),
        sa.Column("causal_chain_id", sa.String(), nullable=True),
        sa.Column("first_detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_findings_domain"), "findings", ["domain"])
    op.create_index(op.f("ix_findings_organization_id"), "findings", ["organization_id"])
    op.create_index(op.f("ix_findings_rule_id"), "findings", ["rule_id"])

    op.create_table(
        "finding_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("finding_id", sa.Uuid(), nullable=False),
        sa.Column("source_system", sa.String(length=100), nullable=False),
        sa.Column("source_record_id", sa.String(length=150), nullable=False),
        sa.Column("evidence_type", sa.String(length=100), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["finding_id"], ["findings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_finding_evidence_finding_id"), "finding_evidence", ["finding_id"])
    op.create_index(
        op.f("ix_finding_evidence_organization_id"),
        "finding_evidence",
        ["organization_id"],
    )

    op.create_table(
        "recovery_actions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("finding_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=250), nullable=False),
        sa.Column("owner", sa.String(length=150), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("expected_recovery", sa.Float(), nullable=False),
        sa.Column("measured_recovery", sa.Float(), nullable=False),
        sa.Column("verified_recovery", sa.Float(), nullable=False),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["finding_id"], ["findings.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_recovery_actions_finding_id"), "recovery_actions", ["finding_id"])
    op.create_index(
        op.f("ix_recovery_actions_organization_id"),
        "recovery_actions",
        ["organization_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_recovery_actions_organization_id"), table_name="recovery_actions")
    op.drop_index(op.f("ix_recovery_actions_finding_id"), table_name="recovery_actions")
    op.drop_table("recovery_actions")
    op.drop_index(op.f("ix_finding_evidence_organization_id"), table_name="finding_evidence")
    op.drop_index(op.f("ix_finding_evidence_finding_id"), table_name="finding_evidence")
    op.drop_table("finding_evidence")
    op.drop_index(op.f("ix_findings_rule_id"), table_name="findings")
    op.drop_index(op.f("ix_findings_organization_id"), table_name="findings")
    op.drop_index(op.f("ix_findings_domain"), table_name="findings")
    op.drop_table("findings")
    op.drop_index(op.f("ix_organizations_slug"), table_name="organizations")
    op.drop_table("organizations")
