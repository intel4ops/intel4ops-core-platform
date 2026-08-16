"""Add Knowledge Pack declarative reference pattern content.

P3.12 needs to author structured reference "leakage pattern" content
(process stage, required evidence, detection preconditions, exclusions,
causal hypotheses, recovery playbook, etc.) directly on a Knowledge Pack
version. No existing table can hold this: KnowledgePackVersion has no
generic content column, and OperationalLearning is single-statement
narrative content curated from independently-governed, already-approved
learnings -- not pack-authored reference knowledge (Reference Knowledge !=
Client-Validated Learning). This adds one small, additive table, scoped
only to the Knowledge Pack framework, mirroring the existing
KnowledgePackLearningLink/KnowledgePackAuditEvent composite-FK shape.

Revision ID: 20260822_0048
Revises: 20260821_0047
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260822_0048"
down_revision: str | None = "20260821_0047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
portable_json = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")

_PROCESS_STAGES = (
    "job_creation",
    "field_execution",
    "evidence_capture",
    "resource_validation",
    "contract_rate_validation",
    "invoicing",
    "payment",
    "recovery",
)
_PROVENANCE_TYPES = ("production", "simulation", "manual", "mixed")


def upgrade() -> None:
    op.create_table(
        "knowledge_pack_patterns",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("knowledge_pack_version_id", sa.Uuid(), nullable=False),
        sa.Column("pattern_key", sa.String(60), nullable=False),
        sa.Column("name", sa.String(250), nullable=False),
        sa.Column("process_stage", sa.String(40), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("provenance_type", sa.String(20), nullable=False),
        sa.Column("content_json", portable_json, nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "knowledge_pack_version_id"],
            ["knowledge_pack_versions.organization_id", "knowledge_pack_versions.id"],
            name="fk_pack_pattern_org_version",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "knowledge_pack_version_id",
            "pattern_key",
            name="uq_pack_pattern_org_version_key",
        ),
        sa.CheckConstraint(
            f"process_stage IN {_PROCESS_STAGES}", name="ck_pack_pattern_process_stage"
        ),
        sa.CheckConstraint(
            f"provenance_type IN {_PROVENANCE_TYPES}", name="ck_pack_pattern_provenance"
        ),
    )
    op.create_index(
        "ix_pack_pattern_org_version",
        "knowledge_pack_patterns",
        ["organization_id", "knowledge_pack_version_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_pack_pattern_org_version", table_name="knowledge_pack_patterns")
    op.drop_table("knowledge_pack_patterns")
