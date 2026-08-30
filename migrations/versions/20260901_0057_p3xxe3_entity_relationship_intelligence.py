"""P3.xxE.3 entity + relationship intelligence

Revision ID: 20260901_0057
Revises: 20260831_0056
Create Date: 2026-09-01 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260901_0057"
down_revision: str | None = "20260831_0056"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ENTITY_TYPES = (
    "ASSET",
    "WORK_ORDER",
    "CUSTOMER",
    "INVOICE",
    "PERSON",
    "PART",
    "LOCATION",
    "CONTRACT",
    "PRODUCT",
    "TRANSACTION",
    "EVENT",
    "OTHER",
)
_RELATIONSHIP_TYPES = (
    "REFERENCES",
    "BELONGS_TO",
    "HAS",
    "USES",
    "GENERATES",
    "PERFORMED_BY",
    "LOCATED_AT",
    "ASSOCIATED_WITH",
)
_CARDINALITIES = ("ONE_TO_ONE", "ONE_TO_MANY", "MANY_TO_ONE", "MANY_TO_MANY", "UNKNOWN")
_RELATIONSHIP_STATUSES = ("AUTO_ACCEPTED", "ACCEPTED_WITH_FLAG", "REVIEW_REQUIRED", "CONFLICTED")


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    op.create_table(
        "canonical_case_entities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_case_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(length=40), nullable=False),
        sa.Column("canonical_key", sa.String(length=300), nullable=False),
        sa.Column("display_label", sa.String(length=300), nullable=False),
        sa.Column("entity_type_confidence", sa.Float(), nullable=False),
        sa.Column("entity_identity_confidence", sa.Float(), nullable=False),
        sa.Column("resolution_method", sa.String(length=20), nullable=False),
        sa.Column(
            "evidence_summary",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("resolution_policy_version", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"entity_type IN ({_quoted(_ENTITY_TYPES)})", name="ck_canonical_case_entity_type"
        ),
        sa.CheckConstraint(
            "entity_type_confidence >= 0 AND entity_type_confidence <= 1",
            name="ck_canonical_case_entity_type_confidence_range",
        ),
        sa.CheckConstraint(
            "entity_identity_confidence >= 0 AND entity_identity_confidence <= 1",
            name="ck_canonical_case_entity_identity_confidence_range",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "analysis_case_id"],
            ["analysis_cases.organization_id", "analysis_cases.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["run_id"], ["analysis_case_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "entity_type",
            "canonical_key",
            name="uq_canonical_case_entity_run_type_key",
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_canonical_case_entities_org_id"),
    )
    op.create_index(
        "ix_canonical_case_entities_org_case_run",
        "canonical_case_entities",
        ["organization_id", "analysis_case_id", "run_id"],
        unique=False,
    )
    op.create_index(
        "ix_canonical_case_entities_run_type",
        "canonical_case_entities",
        ["run_id", "entity_type"],
        unique=False,
    )

    op.create_table(
        "canonical_case_entity_observations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("canonical_entity_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_case_dataset_id", sa.Uuid(), nullable=False),
        sa.Column("source_field", sa.String(length=255), nullable=False),
        sa.Column("concept_code", sa.String(length=100), nullable=False),
        sa.Column("raw_value", sa.String(length=500), nullable=True),
        sa.Column("raw_value_hash", sa.String(length=64), nullable=True),
        sa.Column("normalized_value", sa.String(length=500), nullable=False),
        sa.Column("semantic_confidence", sa.Float(), nullable=False),
        sa.Column("semantic_source", sa.String(length=60), nullable=False),
        sa.Column("human_validated", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "canonical_entity_id"],
            ["canonical_case_entities.organization_id", "canonical_case_entities.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["analysis_case_dataset_id"], ["analysis_case_datasets.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_canonical_case_entity_observations_entity",
        "canonical_case_entity_observations",
        ["canonical_entity_id"],
        unique=False,
    )

    op.create_table(
        "canonical_case_relationships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_case_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("left_entity_id", sa.Uuid(), nullable=False),
        sa.Column("right_entity_id", sa.Uuid(), nullable=False),
        sa.Column("relationship_type", sa.String(length=30), nullable=False),
        sa.Column("cardinality", sa.String(length=20), nullable=False),
        sa.Column("left_entity_identity_confidence", sa.Float(), nullable=False),
        sa.Column("right_entity_identity_confidence", sa.Float(), nullable=False),
        sa.Column("structural_evidence_confidence", sa.Float(), nullable=False),
        sa.Column("relationship_confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column(
            "evidence_summary",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("conflict_reason", sa.Text(), nullable=True),
        sa.Column("relationship_policy_version", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "left_entity_id != right_entity_id", name="ck_canonical_case_rel_no_self"
        ),
        sa.CheckConstraint(
            f"relationship_type IN ({_quoted(_RELATIONSHIP_TYPES)})",
            name="ck_canonical_case_relationship_type",
        ),
        sa.CheckConstraint(
            f"cardinality IN ({_quoted(_CARDINALITIES)})",
            name="ck_canonical_case_relationship_cardinality",
        ),
        sa.CheckConstraint(
            f"status IN ({_quoted(_RELATIONSHIP_STATUSES)})",
            name="ck_canonical_case_relationship_status",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "analysis_case_id"],
            ["analysis_cases.organization_id", "analysis_cases.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "left_entity_id"],
            ["canonical_case_entities.organization_id", "canonical_case_entities.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "right_entity_id"],
            ["canonical_case_entities.organization_id", "canonical_case_entities.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["run_id"], ["analysis_case_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "left_entity_id",
            "right_entity_id",
            "relationship_type",
            name="uq_canonical_case_relationship_run_pair_type",
        ),
    )
    op.create_index(
        "ix_canonical_case_relationships_org_case_run",
        "canonical_case_relationships",
        ["organization_id", "analysis_case_id", "run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_canonical_case_relationships_org_case_run", table_name="canonical_case_relationships"
    )
    op.drop_table("canonical_case_relationships")
    op.drop_index(
        "ix_canonical_case_entity_observations_entity",
        table_name="canonical_case_entity_observations",
    )
    op.drop_table("canonical_case_entity_observations")
    op.drop_index("ix_canonical_case_entities_run_type", table_name="canonical_case_entities")
    op.drop_index("ix_canonical_case_entities_org_case_run", table_name="canonical_case_entities")
    op.drop_table("canonical_case_entities")
