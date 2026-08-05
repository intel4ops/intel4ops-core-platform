from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    event,
    inspect,
    select,
)
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.entities import utc_now
from app.models.source_system import enum_values, portable_json


class CausalNodeType(StrEnum):
    FINDING = "finding"
    CANONICAL_ENTITY = "canonical_entity"
    CANONICAL_EVENT = "canonical_event"
    CANONICAL_METRIC = "canonical_metric"
    OPERATIONAL_ACTION = "operational_action"
    ACTION_OUTCOME = "action_outcome"
    ECONOMIC_IMPACT = "economic_impact"
    EXTERNAL_FACTOR = "external_factor"
    GOVERNED_HYPOTHESIS = "governed_hypothesis"


class CausalEdgeType(StrEnum):
    CAUSES = "causes"
    CONTRIBUTES_TO = "contributes_to"
    PRECEDES = "precedes"
    AMPLIFIES = "amplifies"
    MITIGATES = "mitigates"
    PREVENTS = "prevents"
    CORRELATES_WITH = "correlates_with"
    ASSOCIATED_WITH = "associated_with"
    INFERRED_FROM = "inferred_from"
    CONFIRMED_BY = "confirmed_by"
    CONTRADICTS = "contradicts"
    SUPERSEDES = "supersedes"


ASSOCIATION_ONLY_EDGE_TYPES = (CausalEdgeType.CORRELATES_WITH, CausalEdgeType.ASSOCIATED_WITH)


class CausalMethodClass(StrEnum):
    DETERMINISTIC_TEMPORAL_RULE = "deterministic_temporal_rule"
    BUSINESS_RULE_CAUSALITY = "business_rule_causality"
    SEQUENCE_PATTERN = "sequence_pattern"
    LAGGED_ASSOCIATION = "lagged_association"
    CONDITIONAL_CO_OCCURRENCE = "conditional_co_occurrence"
    EXPERT_CONFIRMED = "expert_confirmed"
    BEFORE_AFTER_INTERVENTION = "before_after_intervention"


class CausalMethodStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    RETIRED = "retired"


class CausalHypothesisStatus(StrEnum):
    DRAFT = "draft"
    PROPOSED = "proposed"
    EVIDENCE_PENDING = "evidence_pending"
    UNDER_REVIEW = "under_review"
    PROBABLE = "probable"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    REVOKED = "revoked"
    ARCHIVED = "archived"


CAUSAL_HYPOTHESIS_TERMINAL_STATUSES = {
    CausalHypothesisStatus.CONFIRMED.value,
    CausalHypothesisStatus.REJECTED.value,
    CausalHypothesisStatus.SUPERSEDED.value,
    CausalHypothesisStatus.REVOKED.value,
    CausalHypothesisStatus.ARCHIVED.value,
}

CAUSAL_HYPOTHESIS_EVIDENCE_IMMUTABLE_STATUSES = {
    CausalHypothesisStatus.PROBABLE.value,
    *CAUSAL_HYPOTHESIS_TERMINAL_STATUSES,
}

CAUSAL_HYPOTHESIS_ALLOWED_TERMINAL_TRANSITIONS = {
    (CausalHypothesisStatus.CONFIRMED.value, CausalHypothesisStatus.SUPERSEDED.value),
    (CausalHypothesisStatus.CONFIRMED.value, CausalHypothesisStatus.REVOKED.value),
    (CausalHypothesisStatus.CONFIRMED.value, CausalHypothesisStatus.ARCHIVED.value),
    (CausalHypothesisStatus.REJECTED.value, CausalHypothesisStatus.ARCHIVED.value),
    (CausalHypothesisStatus.SUPERSEDED.value, CausalHypothesisStatus.ARCHIVED.value),
    (CausalHypothesisStatus.REVOKED.value, CausalHypothesisStatus.ARCHIVED.value),
}


class CausalRole(StrEnum):
    ROOT_CAUSE = "root_cause"
    CONTRIBUTING_CAUSE = "contributing_cause"
    MECHANISM = "mechanism"
    INTERMEDIATE_EFFECT = "intermediate_effect"
    TERMINAL_IMPACT = "terminal_impact"
    INTERVENTION_POINT = "intervention_point"


class CauseCategory(StrEnum):
    STRUCTURAL = "structural"
    BEHAVIORAL = "behavioral"
    EXTERNAL = "external"
    FINANCIAL = "financial"
    OPERATIONAL = "operational"
    TECHNICAL = "technical"
    PROCESS = "process"
    UNKNOWN = "unknown"


class CausalTemporalPrecision(StrEnum):
    INSTANT = "instant"
    SECOND = "second"
    MINUTE = "minute"
    HOUR = "hour"
    DAY = "day"
    PERIOD = "period"


class CausalHardGateOutcome(StrEnum):
    PASSED = "passed"
    BLOCKED = "blocked"


class CausalEvidenceKind(StrEnum):
    FINDING_EVIDENCE = "finding_evidence"
    CALCULATION_TRACE = "calculation_trace"
    RULE_TRACE = "rule_trace"
    CANONICAL_RECORD = "canonical_record"
    LINEAGE_NODE = "lineage_node"
    LINEAGE_EDGE = "lineage_edge"
    LINEAGE_EVENT = "lineage_event"
    SOURCE_CANONICAL_LINK = "source_canonical_link"


class CausalReviewDecision(StrEnum):
    CONFIRM = "confirm"
    PROBABLE = "probable"
    REJECT = "reject"
    DEFER = "defer"
    REVOKE = "revoke"


class CausalChainStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


class CausalTrendDirection(StrEnum):
    INCREASING = "increasing"
    DECREASING = "decreasing"
    STABLE = "stable"
    UNKNOWN = "unknown"


class CausalOutcomeEffect(StrEnum):
    STRENGTHENED = "strengthened"
    WEAKENED = "weakened"
    CONFIRMED = "confirmed"
    REFUTED = "refuted"
    INCONCLUSIVE = "inconclusive"


class CausalGovernedScopeMixin:
    owner_organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=True
    )
    scope_type: Mapped[str] = mapped_column(String(30))
    scope_key: Mapped[str] = mapped_column(String(180))


class CausalTimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class CausalConfidenceMixin:
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    confidence_level: Mapped[str | None] = mapped_column(String(30), nullable=True)
    method_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    method_version: Mapped[str | None] = mapped_column(String(30), nullable=True)
    confidence_components: Mapped[dict[str, object] | None] = mapped_column(
        portable_json, nullable=True
    )
    confidence_interpretation: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_limitations: Mapped[str | None] = mapped_column(Text, nullable=True)
    minimum_supporting_mapping_confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4), nullable=True
    )
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    contradiction_count: Mapped[int] = mapped_column(Integer, default=0)
    review_status: Mapped[str | None] = mapped_column(String(30), nullable=True)


GOVERNED_SCOPE_CHECK = (
    "scope_type IN ('shared_core','industry','regional','organization') "
    "AND ((scope_type = 'organization' AND owner_organization_id IS NOT NULL) "
    "OR (scope_type <> 'organization'))"
)


def _confidence_check(*column_names: str) -> str:
    return " AND ".join(
        f"({name} IS NULL OR ({name} >= 0 AND {name} <= 1))" for name in column_names
    )


class CausalMethodDefinition(CausalGovernedScopeMixin, CausalTimestampMixin, Base):
    __tablename__ = "causal_method_definitions"
    __table_args__ = (
        UniqueConstraint("method_code", "scope_key", name="uq_causal_method_definition_scope"),
        CheckConstraint(GOVERNED_SCOPE_CHECK, name="ck_causal_method_definition_scope"),
        CheckConstraint(
            f"method_class IN ({enum_values(CausalMethodClass)})",
            name="ck_causal_method_definition_class",
        ),
        CheckConstraint(
            f"status IN ({enum_values(CausalMethodStatus)})",
            name="ck_causal_method_definition_status",
        ),
        CheckConstraint(
            "default_confidence_weight >= 0 AND default_confidence_weight <= 1",
            name="ck_causal_method_definition_weight",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_from IS NULL OR effective_to > effective_from",
            name="ck_causal_method_definition_effective_dates",
        ),
        Index("ix_causal_method_definition_code", "method_code"),
        Index("ix_causal_method_definition_owner", "owner_organization_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    method_code: Mapped[str] = mapped_column(String(150))
    method_name: Mapped[str] = mapped_column(String(250))
    method_class: Mapped[str] = mapped_column(String(40))
    method_version: Mapped[str] = mapped_column(String(30))
    default_confidence_weight: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    parameters_schema: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    status: Mapped[str] = mapped_column(String(30), default=CausalMethodStatus.DRAFT.value)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64))


class CausalNode(CausalTimestampMixin, Base):
    __tablename__ = "causal_nodes"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_causal_nodes_org_id"),
        # target_kind/target_id are NULL only for node_type = 'external_factor'; both
        # dialects treat NULLs as distinct in a unique index, so multiple external
        # factors with no backing record remain individually addressable.
        UniqueConstraint(
            "organization_id",
            "node_type",
            "target_kind",
            "target_id",
            name="uq_causal_node_target",
        ),
        CheckConstraint(
            f"node_type IN ({enum_values(CausalNodeType)})",
            name="ck_causal_node_type",
        ),
        CheckConstraint(
            "target_kind IS NULL OR target_kind = node_type",
            name="ck_causal_node_target_kind_match",
        ),
        CheckConstraint(
            f"node_type = '{CausalNodeType.EXTERNAL_FACTOR.value}' "
            "OR (target_kind IS NOT NULL AND target_id IS NOT NULL)",
            name="ck_causal_node_target_required",
        ),
        Index("ix_causal_node_org_type", "organization_id", "node_type"),
        Index("ix_causal_node_org_target", "organization_id", "target_kind", "target_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    node_type: Mapped[str] = mapped_column(String(30))
    target_kind: Mapped[str | None] = mapped_column(String(30), nullable=True)
    target_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    external_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_fingerprint: Mapped[str] = mapped_column(String(64))


class CausalHypothesis(CausalConfidenceMixin, CausalTimestampMixin, Base):
    __tablename__ = "causal_hypotheses"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "source_node_id"],
            ["causal_nodes.organization_id", "causal_nodes.id"],
            name="fk_causal_hypotheses_org_source_node",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "target_node_id"],
            ["causal_nodes.organization_id", "causal_nodes.id"],
            name="fk_causal_hypotheses_org_target_node",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "superseded_by_hypothesis_id"],
            ["causal_hypotheses.organization_id", "causal_hypotheses.id"],
            name="fk_causal_hypotheses_org_superseded_by",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["method_id"],
            ["causal_method_definitions.id"],
            name="fk_causal_hypotheses_method",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "id", name="uq_causal_hypotheses_org_id"),
        UniqueConstraint(
            "organization_id", "content_hash", name="uq_causal_hypothesis_content_hash"
        ),
        CheckConstraint(
            f"proposed_edge_type IN ({enum_values(CausalEdgeType)})",
            name="ck_causal_hypothesis_edge_type",
        ),
        CheckConstraint(
            f"lifecycle_status IN ({enum_values(CausalHypothesisStatus)})",
            name="ck_causal_hypothesis_lifecycle",
        ),
        CheckConstraint(
            "causal_role IS NULL OR causal_role IN (" + enum_values(CausalRole) + ")",
            name="ck_causal_hypothesis_role",
        ),
        CheckConstraint(
            "cause_category IS NULL OR cause_category IN (" + enum_values(CauseCategory) + ")",
            name="ck_causal_hypothesis_cause_category",
        ),
        CheckConstraint(
            "evaluated_temporal_precision IS NULL OR evaluated_temporal_precision IN ("
            + enum_values(CausalTemporalPrecision)
            + ")",
            name="ck_causal_hypothesis_temporal_precision",
        ),
        CheckConstraint(
            "hard_gate_outcome IS NULL OR hard_gate_outcome IN ("
            + enum_values(CausalHardGateOutcome)
            + ")",
            name="ck_causal_hypothesis_gate_outcome",
        ),
        CheckConstraint(
            _confidence_check("confidence_score", "minimum_supporting_mapping_confidence"),
            name="ck_causal_hypothesis_confidence",
        ),
        CheckConstraint(
            "evidence_count >= 0 AND contradiction_count >= 0",
            name="ck_causal_hypothesis_counts",
        ),
        CheckConstraint(
            "validity_to IS NULL OR validity_from IS NULL OR validity_to > validity_from",
            name="ck_causal_hypothesis_validity",
        ),
        CheckConstraint(
            "NOT (proposed_edge_type IN ("
            + ", ".join(f"'{item.value}'" for item in ASSOCIATION_ONLY_EDGE_TYPES)
            + ") AND lifecycle_status = 'confirmed')",
            name="ck_causal_hypothesis_association_not_confirmed",
        ),
        Index("ix_causal_hypothesis_org_status", "organization_id", "lifecycle_status"),
        Index("ix_causal_hypothesis_org_source", "organization_id", "source_node_id"),
        Index("ix_causal_hypothesis_org_target", "organization_id", "target_node_id"),
        Index("ix_causal_hypothesis_method", "method_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    source_node_id: Mapped[UUID] = mapped_column(Uuid)
    target_node_id: Mapped[UUID] = mapped_column(Uuid)
    proposed_edge_type: Mapped[str] = mapped_column(String(30))
    method_id: Mapped[UUID] = mapped_column(Uuid)
    lifecycle_status: Mapped[str] = mapped_column(
        String(30), default=CausalHypothesisStatus.DRAFT.value
    )
    causal_role: Mapped[str | None] = mapped_column(String(30), nullable=True)
    cause_category: Mapped[str | None] = mapped_column(String(30), nullable=True)
    temporal_lag_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evaluated_temporal_precision: Mapped[str | None] = mapped_column(String(20), nullable=True)
    hard_gate_outcome: Mapped[str | None] = mapped_column(String(20), nullable=True)
    hard_gate_failure_reasons: Mapped[list[object]] = mapped_column(portable_json, default=list)
    content_hash: Mapped[str] = mapped_column(String(64))
    superseded_by_hypothesis_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    causal_evaluation_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    validity_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    validity_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid)


class CausalEvidenceLink(CausalTimestampMixin, Base):
    __tablename__ = "causal_evidence_links"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "hypothesis_id"],
            ["causal_hypotheses.organization_id", "causal_hypotheses.id"],
            name="fk_causal_evidence_links_org_hypothesis",
            ondelete="CASCADE",
        ),
        UniqueConstraint("organization_id", "id", name="uq_causal_evidence_links_org_id"),
        UniqueConstraint(
            "hypothesis_id",
            "evidence_kind",
            "evidence_id",
            name="uq_causal_evidence_link_identity",
        ),
        CheckConstraint(
            f"evidence_kind IN ({enum_values(CausalEvidenceKind)})",
            name="ck_causal_evidence_link_kind",
        ),
        CheckConstraint(
            "weight IS NULL OR (weight >= 0 AND weight <= 1)",
            name="ck_causal_evidence_link_weight",
        ),
        Index("ix_causal_evidence_link_org_hypothesis", "organization_id", "hypothesis_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    hypothesis_id: Mapped[UUID] = mapped_column(Uuid)
    evidence_kind: Mapped[str] = mapped_column(String(40))
    evidence_id: Mapped[UUID] = mapped_column(Uuid)
    supports: Mapped[bool] = mapped_column(Boolean, default=True)
    weight: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class CausalReview(CausalTimestampMixin, Base):
    __tablename__ = "causal_reviews"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "hypothesis_id"],
            ["causal_hypotheses.organization_id", "causal_hypotheses.id"],
            name="fk_causal_reviews_org_hypothesis",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "id", name="uq_causal_reviews_org_id"),
        CheckConstraint(
            f"decision IN ({enum_values(CausalReviewDecision)})",
            name="ck_causal_review_decision",
        ),
        Index("ix_causal_review_org_hypothesis", "organization_id", "hypothesis_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    hypothesis_id: Mapped[UUID] = mapped_column(Uuid)
    decision: Mapped[str] = mapped_column(String(30))
    reviewer_user_id: Mapped[UUID] = mapped_column(Uuid)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    limitations_acknowledged: Mapped[str | None] = mapped_column(Text, nullable=True)
    prior_lifecycle_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    resulting_lifecycle_status: Mapped[str | None] = mapped_column(String(30), nullable=True)


class CausalEdge(CausalConfidenceMixin, CausalTimestampMixin, Base):
    __tablename__ = "causal_edges"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "source_node_id"],
            ["causal_nodes.organization_id", "causal_nodes.id"],
            name="fk_causal_edges_org_source_node",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "target_node_id"],
            ["causal_nodes.organization_id", "causal_nodes.id"],
            name="fk_causal_edges_org_target_node",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "hypothesis_id"],
            ["causal_hypotheses.organization_id", "causal_hypotheses.id"],
            name="fk_causal_edges_org_hypothesis",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "id", name="uq_causal_edges_org_id"),
        UniqueConstraint(
            "organization_id",
            "source_node_id",
            "target_node_id",
            "edge_type",
            name="uq_causal_edge_relationship",
        ),
        CheckConstraint(
            f"edge_type IN ({enum_values(CausalEdgeType)})",
            name="ck_causal_edge_type",
        ),
        CheckConstraint(
            "causal_role IS NULL OR causal_role IN (" + enum_values(CausalRole) + ")",
            name="ck_causal_edge_role",
        ),
        CheckConstraint(
            "cause_category IS NULL OR cause_category IN (" + enum_values(CauseCategory) + ")",
            name="ck_causal_edge_cause_category",
        ),
        CheckConstraint(
            _confidence_check("confidence_score", "minimum_supporting_mapping_confidence"),
            name="ck_causal_edge_confidence",
        ),
        CheckConstraint(
            "validity_to IS NULL OR validity_from IS NULL OR validity_to > validity_from",
            name="ck_causal_edge_validity",
        ),
        Index("ix_causal_edge_org_source", "organization_id", "source_node_id", "validity_from"),
        Index("ix_causal_edge_org_target", "organization_id", "target_node_id"),
        Index("ix_causal_edge_org_hypothesis", "organization_id", "hypothesis_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    source_node_id: Mapped[UUID] = mapped_column(Uuid)
    target_node_id: Mapped[UUID] = mapped_column(Uuid)
    hypothesis_id: Mapped[UUID] = mapped_column(Uuid)
    edge_type: Mapped[str] = mapped_column(String(30))
    causal_role: Mapped[str | None] = mapped_column(String(30), nullable=True)
    cause_category: Mapped[str | None] = mapped_column(String(30), nullable=True)
    temporal_lag_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    validity_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    validity_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_primary_path: Mapped[bool] = mapped_column(Boolean, default=False)


class CausalChain(CausalTimestampMixin, Base):
    __tablename__ = "causal_chains"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "root_cause_node_id"],
            ["causal_nodes.organization_id", "causal_nodes.id"],
            name="fk_causal_chains_org_root_cause",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "terminal_impact_node_id"],
            ["causal_nodes.organization_id", "causal_nodes.id"],
            name="fk_causal_chains_org_terminal_impact",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "id", name="uq_causal_chains_org_id"),
        UniqueConstraint("organization_id", "chain_code", name="uq_causal_chain_code"),
        CheckConstraint(
            f"status IN ({enum_values(CausalChainStatus)})",
            name="ck_causal_chain_status",
        ),
        Index("ix_causal_chain_org_root", "organization_id", "root_cause_node_id"),
        Index("ix_causal_chain_org_terminal", "organization_id", "terminal_impact_node_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    chain_code: Mapped[str] = mapped_column(String(150))
    root_cause_node_id: Mapped[UUID] = mapped_column(Uuid)
    terminal_impact_node_id: Mapped[UUID] = mapped_column(Uuid)
    industry_pack_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default=CausalChainStatus.ACTIVE.value)


class CausalChainVersion(Base):
    __tablename__ = "causal_chain_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "chain_id"],
            ["causal_chains.organization_id", "causal_chains.id"],
            name="fk_causal_chain_versions_org_chain",
            ondelete="CASCADE",
        ),
        UniqueConstraint("organization_id", "id", name="uq_causal_chain_versions_org_id"),
        UniqueConstraint("chain_id", "version_number", name="uq_causal_chain_version_number"),
        CheckConstraint("version_number >= 1", name="ck_causal_chain_version_number"),
        CheckConstraint(
            "path_score >= 0 AND path_score <= 1", name="ck_causal_chain_version_path_score"
        ),
        CheckConstraint(
            "weakest_link_confidence IS NULL OR "
            "(weakest_link_confidence >= 0 AND weakest_link_confidence <= 1)",
            name="ck_causal_chain_version_weakest_link",
        ),
        CheckConstraint(
            "trend_direction IS NULL OR trend_direction IN ("
            + enum_values(CausalTrendDirection)
            + ")",
            name="ck_causal_chain_version_trend",
        ),
        CheckConstraint("occurrence_count >= 0", name="ck_causal_chain_version_occurrence_count"),
        Index("ix_causal_chain_version_org_chain", "organization_id", "chain_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    chain_id: Mapped[UUID] = mapped_column(Uuid)
    version_number: Mapped[int] = mapped_column(Integer)
    edge_ids: Mapped[list[object]] = mapped_column(portable_json, default=list)
    path_score: Mapped[Decimal] = mapped_column(Numeric(12, 10))
    weakest_link_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=0)
    first_occurrence_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    latest_occurrence_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    average_recurrence_interval_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trend_direction: Mapped[str | None] = mapped_column(String(20), nullable=True)
    operational_impact_summary: Mapped[dict[str, object] | None] = mapped_column(
        portable_json, nullable=True
    )
    economic_impact_summary: Mapped[dict[str, object] | None] = mapped_column(
        portable_json, nullable=True
    )
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class CausalIntervention(CausalTimestampMixin, Base):
    __tablename__ = "causal_interventions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "action_id"],
            ["operational_actions.organization_id", "operational_actions.id"],
            name="fk_causal_interventions_org_action",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "targeted_node_id"],
            ["causal_nodes.organization_id", "causal_nodes.id"],
            name="fk_causal_interventions_org_node",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "targeted_edge_id"],
            ["causal_edges.organization_id", "causal_edges.id"],
            name="fk_causal_interventions_org_edge",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "id", name="uq_causal_interventions_org_id"),
        CheckConstraint(
            "(targeted_node_id IS NOT NULL AND targeted_edge_id IS NULL) OR "
            "(targeted_node_id IS NULL AND targeted_edge_id IS NOT NULL)",
            name="ck_causal_intervention_target_xor",
        ),
        Index("ix_causal_intervention_org_action", "organization_id", "action_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    action_id: Mapped[UUID] = mapped_column(Uuid)
    targeted_node_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    targeted_edge_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    expected_mechanism: Mapped[str] = mapped_column(Text)
    expected_causal_interruption: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid)


class CausalOutcomeAssessment(CausalTimestampMixin, Base):
    __tablename__ = "causal_outcome_assessments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "intervention_id"],
            ["causal_interventions.organization_id", "causal_interventions.id"],
            name="fk_causal_outcome_assessments_org_intervention",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "action_outcome_id"],
            ["action_outcomes.organization_id", "action_outcomes.id"],
            name="fk_causal_outcome_assessments_org_action_outcome",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "id", name="uq_causal_outcome_assessments_org_id"),
        UniqueConstraint(
            "intervention_id",
            "action_outcome_id",
            name="uq_causal_outcome_assessment_identity",
        ),
        CheckConstraint(
            f"hypothesis_effect IN ({enum_values(CausalOutcomeEffect)})",
            name="ck_causal_outcome_assessment_effect",
        ),
        Index(
            "ix_causal_outcome_assessment_org_intervention",
            "organization_id",
            "intervention_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    intervention_id: Mapped[UUID] = mapped_column(Uuid)
    action_outcome_id: Mapped[UUID] = mapped_column(Uuid)
    hypothesis_effect: Mapped[str] = mapped_column(String(30))
    chain_interrupted: Mapped[bool] = mapped_column(Boolean, default=False)
    assessed_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class CausalAuditEvent(Base):
    __tablename__ = "causal_audit_events"
    __table_args__ = (
        Index("ix_causal_audit_org_time", "organization_id", "occurred_at"),
        Index("ix_causal_audit_entity", "organization_id", "entity_type", "entity_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    event_type: Mapped[str] = mapped_column(String(60))
    entity_type: Mapped[str] = mapped_column(String(60))
    entity_id: Mapped[UUID] = mapped_column(Uuid)
    actor_type: Mapped[str] = mapped_column(String(30))
    actor_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


def _guard_terminal_hypothesis(_: object, __: object, target: CausalHypothesis) -> None:
    state = inspect(target)
    prior = state.attrs.lifecycle_status.history.deleted
    prior_status = prior[0] if prior else target.lifecycle_status
    if prior_status in CAUSAL_HYPOTHESIS_TERMINAL_STATUSES:
        changed = {
            attribute.key
            for attribute in state.mapper.column_attrs
            if state.attrs[attribute.key].history.has_changes()
        }
        allowed_changed_columns = {"lifecycle_status", "updated_at", "superseded_by_hypothesis_id"}
        if changed - allowed_changed_columns:
            raise ValueError("terminal causal hypotheses are immutable")
        if (
            state.attrs.lifecycle_status.history.has_changes()
            and (prior_status, target.lifecycle_status)
            not in CAUSAL_HYPOTHESIS_ALLOWED_TERMINAL_TRANSITIONS
        ):
            raise ValueError("terminal causal hypotheses are immutable")


def _guard_terminal_hypothesis_delete(_: object, __: object, target: CausalHypothesis) -> None:
    if target.lifecycle_status in CAUSAL_HYPOTHESIS_TERMINAL_STATUSES:
        raise ValueError("terminal causal hypotheses are immutable")


def _guard_evidence_mutation(_: object, connection: Connection, target: CausalEvidenceLink) -> None:
    state = inspect(target)
    prior_organization_ids = state.attrs.organization_id.history.deleted
    prior_hypothesis_ids = state.attrs.hypothesis_id.history.deleted
    parent_keys = {
        (target.organization_id, target.hypothesis_id),
        (
            prior_organization_ids[0] if prior_organization_ids else target.organization_id,
            prior_hypothesis_ids[0] if prior_hypothesis_ids else target.hypothesis_id,
        ),
    }
    for organization_id, hypothesis_id in parent_keys:
        lifecycle_status = connection.execute(
            select(CausalHypothesis.lifecycle_status).where(
                CausalHypothesis.organization_id == organization_id,
                CausalHypothesis.id == hypothesis_id,
            )
        ).scalar_one_or_none()
        if lifecycle_status in CAUSAL_HYPOTHESIS_EVIDENCE_IMMUTABLE_STATUSES:
            raise ValueError(
                "causal evidence is immutable after probable or terminal hypothesis status"
            )


def _immutable(*_: object) -> None:
    raise ValueError("this causal intelligence record is immutable")


event.listen(CausalHypothesis, "before_update", _guard_terminal_hypothesis)
event.listen(CausalHypothesis, "before_delete", _guard_terminal_hypothesis_delete)
event.listen(CausalEvidenceLink, "before_insert", _guard_evidence_mutation)
event.listen(CausalEvidenceLink, "before_update", _guard_evidence_mutation)
event.listen(CausalEvidenceLink, "before_delete", _guard_evidence_mutation)
event.listen(CausalReview, "before_update", _immutable)
event.listen(CausalReview, "before_delete", _immutable)
event.listen(CausalChainVersion, "before_update", _immutable)
event.listen(CausalChainVersion, "before_delete", _immutable)
event.listen(CausalIntervention, "before_update", _immutable)
event.listen(CausalIntervention, "before_delete", _immutable)
event.listen(CausalOutcomeAssessment, "before_update", _immutable)
event.listen(CausalOutcomeAssessment, "before_delete", _immutable)
event.listen(CausalAuditEvent, "before_update", _immutable)
event.listen(CausalAuditEvent, "before_delete", _immutable)
