"""Causal links, causal chains and root-cause intelligence.

Revision ID: 20260806_0032
Revises: 20260804_0031
"""

# ruff: noqa: E501

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

revision: str = "20260806_0032"
down_revision: str | None = "20260804_0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB_VARIANT = sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql")

CAUSAL_NODE_TYPES = (
    "'finding','canonical_entity','canonical_event','canonical_metric',"
    "'operational_action','action_outcome','economic_impact','external_factor',"
    "'governed_hypothesis'"
)
CAUSAL_EDGE_TYPES = (
    "'causes','contributes_to','precedes','amplifies','mitigates','prevents',"
    "'correlates_with','associated_with','inferred_from','confirmed_by',"
    "'contradicts','supersedes'"
)
CAUSAL_METHOD_CLASSES = (
    "'deterministic_temporal_rule','business_rule_causality','sequence_pattern',"
    "'lagged_association','conditional_co_occurrence','expert_confirmed',"
    "'before_after_intervention'"
)
CAUSAL_METHOD_STATUSES = "'draft','active','deprecated','retired'"
CAUSAL_HYPOTHESIS_STATUSES = (
    "'draft','proposed','evidence_pending','under_review','probable','confirmed',"
    "'rejected','superseded','revoked','archived'"
)
CAUSAL_ROLES = (
    "'root_cause','contributing_cause','mechanism','intermediate_effect',"
    "'terminal_impact','intervention_point'"
)
CAUSE_CATEGORIES = (
    "'structural','behavioral','external','financial','operational','technical','process','unknown'"
)
CAUSAL_TEMPORAL_PRECISIONS = "'instant','second','minute','hour','day','period'"
CAUSAL_HARD_GATE_OUTCOMES = "'passed','blocked'"
CAUSAL_EVIDENCE_KINDS = (
    "'finding_evidence','calculation_trace','rule_trace','canonical_record',"
    "'lineage_node','lineage_edge','lineage_event','source_canonical_link'"
)
CAUSAL_REVIEW_DECISIONS = "'confirm','probable','reject','defer','revoke'"
CAUSAL_CHAIN_STATUSES = "'active','superseded','archived'"
CAUSAL_TREND_DIRECTIONS = "'increasing','decreasing','stable','unknown'"
CAUSAL_OUTCOME_EFFECTS = "'strengthened','weakened','confirmed','refuted','inconclusive'"
GOVERNED_SCOPE_CHECK = (
    "scope_type IN ('shared_core','industry','regional','organization') "
    "AND ((scope_type = 'organization' AND owner_organization_id IS NOT NULL) "
    "OR (scope_type <> 'organization'))"
)


def _assert_clean_action_outcome_parent_keys() -> None:
    duplicates = op.get_bind().scalar(
        sa.text(
            """
            SELECT count(*)
            FROM (
                SELECT organization_id, id
                FROM action_outcomes
                GROUP BY organization_id, id
                HAVING count(*) > 1
            ) AS duplicate_targets
            """
        )
    )
    if duplicates:
        raise RuntimeError(
            f"uq_action_outcomes_org_id precondition failed with {duplicates} duplicate targets"
        )


def upgrade() -> None:
    offline = context.is_offline_mode()
    if not offline:
        _assert_clean_action_outcome_parent_keys()

    with op.batch_alter_table("action_outcomes") as batch_op:
        batch_op.create_unique_constraint(
            "uq_action_outcomes_org_id",
            ["organization_id", "id"],
        )

    op.create_table(
        "causal_method_definitions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("method_code", sa.String(length=150), nullable=False),
        sa.Column("method_name", sa.String(length=250), nullable=False),
        sa.Column("method_class", sa.String(length=40), nullable=False),
        sa.Column("method_version", sa.String(length=30), nullable=False),
        sa.Column("default_confidence_weight", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("parameters_schema", JSONB_VARIANT, nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("owner_organization_id", sa.Uuid(), nullable=True),
        sa.Column("scope_type", sa.String(length=30), nullable=False),
        sa.Column("scope_key", sa.String(length=180), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(GOVERNED_SCOPE_CHECK, name="ck_causal_method_definition_scope"),
        sa.CheckConstraint(
            f"method_class IN ({CAUSAL_METHOD_CLASSES})",
            name="ck_causal_method_definition_class",
        ),
        sa.CheckConstraint(
            f"status IN ({CAUSAL_METHOD_STATUSES})",
            name="ck_causal_method_definition_status",
        ),
        sa.CheckConstraint(
            "default_confidence_weight >= 0 AND default_confidence_weight <= 1",
            name="ck_causal_method_definition_weight",
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_from IS NULL OR effective_to > effective_from",
            name="ck_causal_method_definition_effective_dates",
        ),
        sa.ForeignKeyConstraint(
            ["owner_organization_id"], ["organizations.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("method_code", "scope_key", name="uq_causal_method_definition_scope"),
    )
    op.create_index(
        "ix_causal_method_definition_code",
        "causal_method_definitions",
        ["method_code"],
        unique=False,
    )
    op.create_index(
        "ix_causal_method_definition_owner",
        "causal_method_definitions",
        ["owner_organization_id"],
        unique=False,
    )

    op.create_table(
        "causal_nodes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("node_type", sa.String(length=30), nullable=False),
        sa.Column("target_kind", sa.String(length=30), nullable=True),
        sa.Column("target_id", sa.Uuid(), nullable=True),
        sa.Column("external_description", sa.Text(), nullable=True),
        sa.Column("content_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(f"node_type IN ({CAUSAL_NODE_TYPES})", name="ck_causal_node_type"),
        sa.CheckConstraint(
            "target_kind IS NULL OR target_kind = node_type",
            name="ck_causal_node_target_kind_match",
        ),
        sa.CheckConstraint(
            "node_type = 'external_factor' OR (target_kind IS NOT NULL AND target_id IS NOT NULL)",
            name="ck_causal_node_target_required",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_causal_nodes_org_id"),
        sa.UniqueConstraint(
            "organization_id",
            "node_type",
            "target_kind",
            "target_id",
            name="uq_causal_node_target",
        ),
    )
    op.create_index(
        "ix_causal_node_org_type", "causal_nodes", ["organization_id", "node_type"], unique=False
    )
    op.create_index(
        "ix_causal_node_org_target",
        "causal_nodes",
        ["organization_id", "target_kind", "target_id"],
        unique=False,
    )

    op.create_table(
        "causal_hypotheses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("source_node_id", sa.Uuid(), nullable=False),
        sa.Column("target_node_id", sa.Uuid(), nullable=False),
        sa.Column("proposed_edge_type", sa.String(length=30), nullable=False),
        sa.Column("method_id", sa.Uuid(), nullable=False),
        sa.Column("lifecycle_status", sa.String(length=30), nullable=False),
        sa.Column("causal_role", sa.String(length=30), nullable=True),
        sa.Column("cause_category", sa.String(length=30), nullable=True),
        sa.Column("temporal_lag_seconds", sa.Integer(), nullable=True),
        sa.Column("evaluated_temporal_precision", sa.String(length=20), nullable=True),
        sa.Column("hard_gate_outcome", sa.String(length=20), nullable=True),
        sa.Column("hard_gate_failure_reasons", JSONB_VARIANT, nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("superseded_by_hypothesis_id", sa.Uuid(), nullable=True),
        sa.Column("causal_evaluation_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("validity_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("validity_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("confidence_score", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("confidence_level", sa.String(length=30), nullable=True),
        sa.Column("method_code", sa.String(length=100), nullable=True),
        sa.Column("method_version", sa.String(length=30), nullable=True),
        sa.Column("confidence_components", JSONB_VARIANT, nullable=True),
        sa.Column("confidence_interpretation", sa.Text(), nullable=True),
        sa.Column("confidence_limitations", sa.Text(), nullable=True),
        sa.Column(
            "minimum_supporting_mapping_confidence",
            sa.Numeric(precision=5, scale=4),
            nullable=True,
        ),
        sa.Column("evidence_count", sa.Integer(), nullable=False),
        sa.Column("contradiction_count", sa.Integer(), nullable=False),
        sa.Column("review_status", sa.String(length=30), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"proposed_edge_type IN ({CAUSAL_EDGE_TYPES})", name="ck_causal_hypothesis_edge_type"
        ),
        sa.CheckConstraint(
            f"lifecycle_status IN ({CAUSAL_HYPOTHESIS_STATUSES})",
            name="ck_causal_hypothesis_lifecycle",
        ),
        sa.CheckConstraint(
            f"causal_role IS NULL OR causal_role IN ({CAUSAL_ROLES})",
            name="ck_causal_hypothesis_role",
        ),
        sa.CheckConstraint(
            f"cause_category IS NULL OR cause_category IN ({CAUSE_CATEGORIES})",
            name="ck_causal_hypothesis_cause_category",
        ),
        sa.CheckConstraint(
            "evaluated_temporal_precision IS NULL OR evaluated_temporal_precision IN "
            f"({CAUSAL_TEMPORAL_PRECISIONS})",
            name="ck_causal_hypothesis_temporal_precision",
        ),
        sa.CheckConstraint(
            f"hard_gate_outcome IS NULL OR hard_gate_outcome IN ({CAUSAL_HARD_GATE_OUTCOMES})",
            name="ck_causal_hypothesis_gate_outcome",
        ),
        sa.CheckConstraint(
            "(confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)) "
            "AND (minimum_supporting_mapping_confidence IS NULL OR "
            "(minimum_supporting_mapping_confidence >= 0 AND "
            "minimum_supporting_mapping_confidence <= 1))",
            name="ck_causal_hypothesis_confidence",
        ),
        sa.CheckConstraint(
            "evidence_count >= 0 AND contradiction_count >= 0",
            name="ck_causal_hypothesis_counts",
        ),
        sa.CheckConstraint(
            "validity_to IS NULL OR validity_from IS NULL OR validity_to > validity_from",
            name="ck_causal_hypothesis_validity",
        ),
        sa.CheckConstraint(
            "NOT (proposed_edge_type IN ('correlates_with', 'associated_with') "
            "AND lifecycle_status = 'confirmed')",
            name="ck_causal_hypothesis_association_not_confirmed",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["organization_id", "source_node_id"],
            ["causal_nodes.organization_id", "causal_nodes.id"],
            name="fk_causal_hypotheses_org_source_node",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "target_node_id"],
            ["causal_nodes.organization_id", "causal_nodes.id"],
            name="fk_causal_hypotheses_org_target_node",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "superseded_by_hypothesis_id"],
            ["causal_hypotheses.organization_id", "causal_hypotheses.id"],
            name="fk_causal_hypotheses_org_superseded_by",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["method_id"],
            ["causal_method_definitions.id"],
            name="fk_causal_hypotheses_method",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_causal_hypotheses_org_id"),
        sa.UniqueConstraint(
            "organization_id", "content_hash", name="uq_causal_hypothesis_content_hash"
        ),
    )
    op.create_index(
        "ix_causal_hypothesis_org_status",
        "causal_hypotheses",
        ["organization_id", "lifecycle_status"],
        unique=False,
    )
    op.create_index(
        "ix_causal_hypothesis_org_source",
        "causal_hypotheses",
        ["organization_id", "source_node_id"],
        unique=False,
    )
    op.create_index(
        "ix_causal_hypothesis_org_target",
        "causal_hypotheses",
        ["organization_id", "target_node_id"],
        unique=False,
    )
    op.create_index("ix_causal_hypothesis_method", "causal_hypotheses", ["method_id"], unique=False)

    op.create_table(
        "causal_evidence_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("hypothesis_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_kind", sa.String(length=40), nullable=False),
        sa.Column("evidence_id", sa.Uuid(), nullable=False),
        sa.Column("supports", sa.Boolean(), nullable=False),
        sa.Column("weight", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"evidence_kind IN ({CAUSAL_EVIDENCE_KINDS})", name="ck_causal_evidence_link_kind"
        ),
        sa.CheckConstraint(
            "weight IS NULL OR (weight >= 0 AND weight <= 1)",
            name="ck_causal_evidence_link_weight",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["organization_id", "hypothesis_id"],
            ["causal_hypotheses.organization_id", "causal_hypotheses.id"],
            name="fk_causal_evidence_links_org_hypothesis",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_causal_evidence_links_org_id"),
        sa.UniqueConstraint(
            "hypothesis_id",
            "evidence_kind",
            "evidence_id",
            name="uq_causal_evidence_link_identity",
        ),
    )
    op.create_index(
        "ix_causal_evidence_link_org_hypothesis",
        "causal_evidence_links",
        ["organization_id", "hypothesis_id"],
        unique=False,
    )

    op.create_table(
        "causal_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("hypothesis_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(length=30), nullable=False),
        sa.Column("reviewer_user_id", sa.Uuid(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("evidence_summary", sa.Text(), nullable=True),
        sa.Column("limitations_acknowledged", sa.Text(), nullable=True),
        sa.Column("prior_lifecycle_status", sa.String(length=30), nullable=True),
        sa.Column("resulting_lifecycle_status", sa.String(length=30), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"decision IN ({CAUSAL_REVIEW_DECISIONS})", name="ck_causal_review_decision"
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["organization_id", "hypothesis_id"],
            ["causal_hypotheses.organization_id", "causal_hypotheses.id"],
            name="fk_causal_reviews_org_hypothesis",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_causal_reviews_org_id"),
    )
    op.create_index(
        "ix_causal_review_org_hypothesis",
        "causal_reviews",
        ["organization_id", "hypothesis_id"],
        unique=False,
    )

    op.create_table(
        "causal_edges",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("source_node_id", sa.Uuid(), nullable=False),
        sa.Column("target_node_id", sa.Uuid(), nullable=False),
        sa.Column("hypothesis_id", sa.Uuid(), nullable=False),
        sa.Column("edge_type", sa.String(length=30), nullable=False),
        sa.Column("causal_role", sa.String(length=30), nullable=True),
        sa.Column("cause_category", sa.String(length=30), nullable=True),
        sa.Column("temporal_lag_seconds", sa.Integer(), nullable=True),
        sa.Column("validity_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("validity_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_primary_path", sa.Boolean(), nullable=False),
        sa.Column("confidence_score", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("confidence_level", sa.String(length=30), nullable=True),
        sa.Column("method_code", sa.String(length=100), nullable=True),
        sa.Column("method_version", sa.String(length=30), nullable=True),
        sa.Column("confidence_components", JSONB_VARIANT, nullable=True),
        sa.Column("confidence_interpretation", sa.Text(), nullable=True),
        sa.Column("confidence_limitations", sa.Text(), nullable=True),
        sa.Column(
            "minimum_supporting_mapping_confidence",
            sa.Numeric(precision=5, scale=4),
            nullable=True,
        ),
        sa.Column("evidence_count", sa.Integer(), nullable=False),
        sa.Column("contradiction_count", sa.Integer(), nullable=False),
        sa.Column("review_status", sa.String(length=30), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(f"edge_type IN ({CAUSAL_EDGE_TYPES})", name="ck_causal_edge_type"),
        sa.CheckConstraint(
            f"causal_role IS NULL OR causal_role IN ({CAUSAL_ROLES})",
            name="ck_causal_edge_role",
        ),
        sa.CheckConstraint(
            f"cause_category IS NULL OR cause_category IN ({CAUSE_CATEGORIES})",
            name="ck_causal_edge_cause_category",
        ),
        sa.CheckConstraint(
            "(confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)) "
            "AND (minimum_supporting_mapping_confidence IS NULL OR "
            "(minimum_supporting_mapping_confidence >= 0 AND "
            "minimum_supporting_mapping_confidence <= 1))",
            name="ck_causal_edge_confidence",
        ),
        sa.CheckConstraint(
            "validity_to IS NULL OR validity_from IS NULL OR validity_to > validity_from",
            name="ck_causal_edge_validity",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["organization_id", "source_node_id"],
            ["causal_nodes.organization_id", "causal_nodes.id"],
            name="fk_causal_edges_org_source_node",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "target_node_id"],
            ["causal_nodes.organization_id", "causal_nodes.id"],
            name="fk_causal_edges_org_target_node",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "hypothesis_id"],
            ["causal_hypotheses.organization_id", "causal_hypotheses.id"],
            name="fk_causal_edges_org_hypothesis",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_causal_edges_org_id"),
        sa.UniqueConstraint(
            "organization_id",
            "source_node_id",
            "target_node_id",
            "edge_type",
            name="uq_causal_edge_relationship",
        ),
    )
    op.create_index(
        "ix_causal_edge_org_source",
        "causal_edges",
        ["organization_id", "source_node_id", "validity_from"],
        unique=False,
    )
    op.create_index(
        "ix_causal_edge_org_target",
        "causal_edges",
        ["organization_id", "target_node_id"],
        unique=False,
    )
    op.create_index(
        "ix_causal_edge_org_hypothesis",
        "causal_edges",
        ["organization_id", "hypothesis_id"],
        unique=False,
    )

    op.create_table(
        "causal_chains",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("chain_code", sa.String(length=150), nullable=False),
        sa.Column("root_cause_node_id", sa.Uuid(), nullable=False),
        sa.Column("terminal_impact_node_id", sa.Uuid(), nullable=False),
        sa.Column("industry_pack_code", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(f"status IN ({CAUSAL_CHAIN_STATUSES})", name="ck_causal_chain_status"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["organization_id", "root_cause_node_id"],
            ["causal_nodes.organization_id", "causal_nodes.id"],
            name="fk_causal_chains_org_root_cause",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "terminal_impact_node_id"],
            ["causal_nodes.organization_id", "causal_nodes.id"],
            name="fk_causal_chains_org_terminal_impact",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_causal_chains_org_id"),
        sa.UniqueConstraint("organization_id", "chain_code", name="uq_causal_chain_code"),
    )
    op.create_index(
        "ix_causal_chain_org_root",
        "causal_chains",
        ["organization_id", "root_cause_node_id"],
        unique=False,
    )
    op.create_index(
        "ix_causal_chain_org_terminal",
        "causal_chains",
        ["organization_id", "terminal_impact_node_id"],
        unique=False,
    )

    op.create_table(
        "causal_chain_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("chain_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("edge_ids", JSONB_VARIANT, nullable=False),
        sa.Column("path_score", sa.Numeric(precision=12, scale=10), nullable=False),
        sa.Column("weakest_link_confidence", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("occurrence_count", sa.Integer(), nullable=False),
        sa.Column("first_occurrence_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latest_occurrence_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("average_recurrence_interval_seconds", sa.Integer(), nullable=True),
        sa.Column("trend_direction", sa.String(length=20), nullable=True),
        sa.Column("operational_impact_summary", JSONB_VARIANT, nullable=True),
        sa.Column("economic_impact_summary", JSONB_VARIANT, nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version_number >= 1", name="ck_causal_chain_version_number"),
        sa.CheckConstraint(
            "path_score >= 0 AND path_score <= 1", name="ck_causal_chain_version_path_score"
        ),
        sa.CheckConstraint(
            "weakest_link_confidence IS NULL OR "
            "(weakest_link_confidence >= 0 AND weakest_link_confidence <= 1)",
            name="ck_causal_chain_version_weakest_link",
        ),
        sa.CheckConstraint(
            f"trend_direction IS NULL OR trend_direction IN ({CAUSAL_TREND_DIRECTIONS})",
            name="ck_causal_chain_version_trend",
        ),
        sa.CheckConstraint(
            "occurrence_count >= 0", name="ck_causal_chain_version_occurrence_count"
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["organization_id", "chain_id"],
            ["causal_chains.organization_id", "causal_chains.id"],
            name="fk_causal_chain_versions_org_chain",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_causal_chain_versions_org_id"),
        sa.UniqueConstraint("chain_id", "version_number", name="uq_causal_chain_version_number"),
    )
    op.create_index(
        "ix_causal_chain_version_org_chain",
        "causal_chain_versions",
        ["organization_id", "chain_id"],
        unique=False,
    )

    op.create_table(
        "causal_interventions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("action_id", sa.Uuid(), nullable=False),
        sa.Column("targeted_node_id", sa.Uuid(), nullable=True),
        sa.Column("targeted_edge_id", sa.Uuid(), nullable=True),
        sa.Column("expected_mechanism", sa.Text(), nullable=False),
        sa.Column("expected_causal_interruption", sa.Boolean(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(targeted_node_id IS NOT NULL AND targeted_edge_id IS NULL) OR "
            "(targeted_node_id IS NULL AND targeted_edge_id IS NOT NULL)",
            name="ck_causal_intervention_target_xor",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["organization_id", "action_id"],
            ["operational_actions.organization_id", "operational_actions.id"],
            name="fk_causal_interventions_org_action",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "targeted_node_id"],
            ["causal_nodes.organization_id", "causal_nodes.id"],
            name="fk_causal_interventions_org_node",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "targeted_edge_id"],
            ["causal_edges.organization_id", "causal_edges.id"],
            name="fk_causal_interventions_org_edge",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_causal_interventions_org_id"),
    )
    op.create_index(
        "ix_causal_intervention_org_action",
        "causal_interventions",
        ["organization_id", "action_id"],
        unique=False,
    )

    op.create_table(
        "causal_outcome_assessments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("intervention_id", sa.Uuid(), nullable=False),
        sa.Column("action_outcome_id", sa.Uuid(), nullable=False),
        sa.Column("hypothesis_effect", sa.String(length=30), nullable=False),
        sa.Column("chain_interrupted", sa.Boolean(), nullable=False),
        sa.Column("assessed_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("evidence_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"hypothesis_effect IN ({CAUSAL_OUTCOME_EFFECTS})",
            name="ck_causal_outcome_assessment_effect",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["organization_id", "intervention_id"],
            ["causal_interventions.organization_id", "causal_interventions.id"],
            name="fk_causal_outcome_assessments_org_intervention",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "action_outcome_id"],
            ["action_outcomes.organization_id", "action_outcomes.id"],
            name="fk_causal_outcome_assessments_org_action_outcome",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_causal_outcome_assessments_org_id"),
        sa.UniqueConstraint(
            "intervention_id",
            "action_outcome_id",
            name="uq_causal_outcome_assessment_identity",
        ),
    )
    op.create_index(
        "ix_causal_outcome_assessment_org_intervention",
        "causal_outcome_assessments",
        ["organization_id", "intervention_id"],
        unique=False,
    )

    op.create_table(
        "causal_audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column("entity_type", sa.String(length=60), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("actor_type", sa.String(length=30), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("metadata_json", JSONB_VARIANT, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_causal_audit_org_time",
        "causal_audit_events",
        ["organization_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_causal_audit_entity",
        "causal_audit_events",
        ["organization_id", "entity_type", "entity_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_causal_audit_entity", table_name="causal_audit_events")
    op.drop_index("ix_causal_audit_org_time", table_name="causal_audit_events")
    op.drop_table("causal_audit_events")

    op.drop_index(
        "ix_causal_outcome_assessment_org_intervention",
        table_name="causal_outcome_assessments",
    )
    op.drop_table("causal_outcome_assessments")

    op.drop_index("ix_causal_intervention_org_action", table_name="causal_interventions")
    op.drop_table("causal_interventions")

    op.drop_index("ix_causal_chain_version_org_chain", table_name="causal_chain_versions")
    op.drop_table("causal_chain_versions")

    op.drop_index("ix_causal_chain_org_terminal", table_name="causal_chains")
    op.drop_index("ix_causal_chain_org_root", table_name="causal_chains")
    op.drop_table("causal_chains")

    op.drop_index("ix_causal_edge_org_hypothesis", table_name="causal_edges")
    op.drop_index("ix_causal_edge_org_target", table_name="causal_edges")
    op.drop_index("ix_causal_edge_org_source", table_name="causal_edges")
    op.drop_table("causal_edges")

    op.drop_index("ix_causal_review_org_hypothesis", table_name="causal_reviews")
    op.drop_table("causal_reviews")

    op.drop_index("ix_causal_evidence_link_org_hypothesis", table_name="causal_evidence_links")
    op.drop_table("causal_evidence_links")

    op.drop_index("ix_causal_hypothesis_method", table_name="causal_hypotheses")
    op.drop_index("ix_causal_hypothesis_org_target", table_name="causal_hypotheses")
    op.drop_index("ix_causal_hypothesis_org_source", table_name="causal_hypotheses")
    op.drop_index("ix_causal_hypothesis_org_status", table_name="causal_hypotheses")
    op.drop_table("causal_hypotheses")

    op.drop_index("ix_causal_node_org_target", table_name="causal_nodes")
    op.drop_index("ix_causal_node_org_type", table_name="causal_nodes")
    op.drop_table("causal_nodes")

    op.drop_index("ix_causal_method_definition_owner", table_name="causal_method_definitions")
    op.drop_index("ix_causal_method_definition_code", table_name="causal_method_definitions")
    op.drop_table("causal_method_definitions")

    with op.batch_alter_table("action_outcomes") as batch_op:
        batch_op.drop_constraint("uq_action_outcomes_org_id", type_="unique")
