"""Add governed operational learning and source-case provenance.

Revision ID: 20260819_0045
Revises: 20260818_0044
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260819_0045"
down_revision: str | None = "20260818_0044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
portable_json = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "operational_learnings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("learning_type", sa.String(40), nullable=False),
        sa.Column("title", sa.String(250), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("provenance_type", sa.String(20), nullable=False),
        sa.Column("value_basis", sa.String(30), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("reviewed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "id", name="uq_operational_learning_org_id"),
        sa.CheckConstraint(
            "learning_type IN ('operational_pattern','corrective_action',"
            "'causal_observation','execution_playbook','risk_indicator',"
            "'verification_pattern')",
            name="ck_learning_type",
        ),
        sa.CheckConstraint(
            "status IN ('candidate','reviewed','approved_for_reuse','rejected','retired')",
            name="ck_learning_status",
        ),
        sa.CheckConstraint(
            "provenance_type IN ('production','simulation','manual','mixed')",
            name="ck_learning_provenance",
        ),
        sa.CheckConstraint(
            "value_basis IN ('none','expected','realized_measurement','verified_ledger')",
            name="ck_learning_value_basis",
        ),
    )
    op.create_index(
        "ix_learning_org_status_created",
        "operational_learnings",
        ["organization_id", "status", "created_at"],
    )
    op.create_index(
        "ix_learning_org_provenance",
        "operational_learnings",
        ["organization_id", "provenance_type"],
    )
    op.create_table(
        "learning_source_cases",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("learning_id", sa.Uuid(), nullable=False),
        sa.Column(
            "finding_id",
            sa.Uuid(),
            sa.ForeignKey("findings.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("provenance_type", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("learning_id", "finding_id", name="uq_learning_source_case"),
        sa.ForeignKeyConstraint(
            ["organization_id", "learning_id"],
            ["operational_learnings.organization_id", "operational_learnings.id"],
            name="fk_learning_source_org_learning",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_learning_source_org_finding", "learning_source_cases", ["organization_id", "finding_id"]
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            """
            CREATE FUNCTION enforce_learning_source_finding_tenant()
            RETURNS trigger AS $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM findings
                    WHERE id = NEW.finding_id
                      AND organization_id = NEW.organization_id
                ) THEN
                    RAISE EXCEPTION 'learning source finding must belong to organization';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_learning_source_finding_tenant
            BEFORE INSERT OR UPDATE ON learning_source_cases
            FOR EACH ROW EXECUTE FUNCTION enforce_learning_source_finding_tenant()
            """
        )
    else:
        op.execute(
            """
            CREATE TRIGGER trg_learning_source_finding_tenant
            BEFORE INSERT ON learning_source_cases
            FOR EACH ROW
            WHEN NOT EXISTS (
                SELECT 1 FROM findings
                WHERE id = NEW.finding_id
                  AND organization_id = NEW.organization_id
            )
            BEGIN
                SELECT RAISE(ABORT, 'learning source finding must belong to organization');
            END
            """
        )
    op.create_table(
        "learning_audit_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("learning_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("prior_status", sa.String(30), nullable=True),
        sa.Column("new_status", sa.String(30), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("actor_role", sa.String(50), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("metadata_json", portable_json, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "learning_id"],
            ["operational_learnings.organization_id", "operational_learnings.id"],
            name="fk_learning_audit_org_learning",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_learning_audit_org_learning",
        "learning_audit_events",
        ["organization_id", "learning_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_table("learning_audit_events")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER trg_learning_source_finding_tenant ON learning_source_cases")
        op.execute("DROP FUNCTION enforce_learning_source_finding_tenant()")
    op.drop_table("learning_source_cases")
    op.drop_table("operational_learnings")
