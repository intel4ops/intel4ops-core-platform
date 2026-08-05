from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ScopeType = Literal["shared_core", "industry", "regional", "organization"]
CausalMethodClassLiteral = Literal[
    "deterministic_temporal_rule",
    "business_rule_causality",
    "sequence_pattern",
    "lagged_association",
    "conditional_co_occurrence",
    "expert_confirmed",
    "before_after_intervention",
]
CausalNodeTypeLiteral = Literal[
    "finding",
    "canonical_entity",
    "canonical_event",
    "canonical_metric",
    "operational_action",
    "action_outcome",
    "economic_impact",
    "external_factor",
    "governed_hypothesis",
]
CausalEdgeTypeLiteral = Literal[
    "causes",
    "contributes_to",
    "precedes",
    "amplifies",
    "mitigates",
    "prevents",
    "correlates_with",
    "associated_with",
    "inferred_from",
    "confirmed_by",
    "contradicts",
    "supersedes",
]
CausalRoleLiteral = Literal[
    "root_cause",
    "contributing_cause",
    "mechanism",
    "intermediate_effect",
    "terminal_impact",
    "intervention_point",
]
CauseCategoryLiteral = Literal[
    "structural",
    "behavioral",
    "external",
    "financial",
    "operational",
    "technical",
    "process",
    "unknown",
]
CausalEvidenceKindLiteral = Literal[
    "finding_evidence",
    "calculation_trace",
    "rule_trace",
    "canonical_record",
    "lineage_node",
    "lineage_edge",
    "lineage_event",
    "source_canonical_link",
]
CausalReviewDecisionLiteral = Literal["confirm", "probable", "reject", "defer", "revoke"]
CausalOutcomeEffectLiteral = Literal[
    "strengthened", "weakened", "confirmed", "refuted", "inconclusive"
]


class CausalMethodDefinitionCreate(BaseModel):
    method_code: str = Field(min_length=2, max_length=150, pattern=r"^[a-z][a-z0-9_]*$")
    method_name: str = Field(min_length=1, max_length=250)
    method_class: CausalMethodClassLiteral
    method_version: str = Field(pattern=r"^\d+\.\d+\.\d+$", max_length=30)
    default_confidence_weight: Decimal = Field(ge=0, le=1)
    parameters_schema: dict[str, object] = Field(default_factory=dict)
    scope_type: ScopeType
    scope_key: str = Field(min_length=1, max_length=180)
    owner_organization_id: UUID | None = None
    effective_from: datetime | None = None
    effective_to: datetime | None = None


class CausalMethodDefinitionRead(CausalMethodDefinitionCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: str
    content_hash: str
    created_at: datetime
    updated_at: datetime


class CausalNodeCreate(BaseModel):
    node_type: CausalNodeTypeLiteral
    target_id: UUID | None = None
    external_description: str | None = None


class CausalNodeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    node_type: str
    target_kind: str | None
    target_id: UUID | None
    external_description: str | None
    content_fingerprint: str
    created_at: datetime
    updated_at: datetime


class CausalHypothesisCreate(BaseModel):
    source_node_id: UUID
    target_node_id: UUID
    proposed_edge_type: CausalEdgeTypeLiteral
    method_id: UUID
    causal_role: CausalRoleLiteral | None = None
    cause_category: CauseCategoryLiteral | None = None
    temporal_lag_seconds: int | None = None
    validity_from: datetime | None = None
    validity_to: datetime | None = None


class CausalHypothesisRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    source_node_id: UUID
    target_node_id: UUID
    proposed_edge_type: str
    method_id: UUID
    lifecycle_status: str
    causal_role: str | None
    cause_category: str | None
    temporal_lag_seconds: int | None
    evaluated_temporal_precision: str | None
    hard_gate_outcome: str | None
    hard_gate_failure_reasons: list[object]
    content_hash: str
    superseded_by_hypothesis_id: UUID | None
    causal_evaluation_time: datetime | None
    validity_from: datetime | None
    validity_to: datetime | None
    confidence_score: Decimal | None
    confidence_level: str | None
    method_code: str | None
    method_version: str | None
    confidence_components: dict[str, object] | None
    confidence_interpretation: str | None
    confidence_limitations: str | None
    minimum_supporting_mapping_confidence: Decimal | None
    evidence_count: int
    contradiction_count: int
    review_status: str | None
    created_by_user_id: UUID
    created_at: datetime
    updated_at: datetime


class CausalEvidenceLinkCreate(BaseModel):
    evidence_kind: CausalEvidenceKindLiteral
    evidence_id: UUID
    supports: bool = True
    weight: Decimal | None = Field(default=None, ge=0, le=1)
    notes: str | None = None


class CausalEvidenceLinkRead(CausalEvidenceLinkCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    hypothesis_id: UUID
    recorded_at: datetime
    created_at: datetime
    updated_at: datetime


class CausalReviewCreate(BaseModel):
    decision: CausalReviewDecisionLiteral
    notes: str | None = None
    evidence_summary: str | None = None
    limitations_acknowledged: str | None = None


class CausalReviewRead(CausalReviewCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    hypothesis_id: UUID
    reviewer_user_id: UUID
    reviewed_at: datetime
    prior_lifecycle_status: str | None
    resulting_lifecycle_status: str | None
    created_at: datetime
    updated_at: datetime


class CausalEdgeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    source_node_id: UUID
    target_node_id: UUID
    hypothesis_id: UUID
    edge_type: str
    causal_role: str | None
    cause_category: str | None
    temporal_lag_seconds: int | None
    validity_from: datetime | None
    validity_to: datetime | None
    is_primary_path: bool
    confidence_score: Decimal | None
    confidence_level: str | None
    evidence_count: int
    contradiction_count: int
    created_at: datetime
    updated_at: datetime


class CausalChainRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    chain_code: str
    root_cause_node_id: UUID
    terminal_impact_node_id: UUID
    industry_pack_code: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class CausalChainVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    chain_id: UUID
    version_number: int
    edge_ids: list[object]
    path_score: Decimal
    weakest_link_confidence: Decimal | None
    occurrence_count: int
    first_occurrence_at: datetime | None
    latest_occurrence_at: datetime | None
    average_recurrence_interval_seconds: int | None
    trend_direction: str | None
    operational_impact_summary: dict[str, object] | None
    economic_impact_summary: dict[str, object] | None
    computed_at: datetime


class CausalInterventionCreate(BaseModel):
    action_id: UUID
    targeted_node_id: UUID | None = None
    targeted_edge_id: UUID | None = None
    expected_mechanism: str = Field(min_length=1)
    expected_causal_interruption: bool = False


class CausalInterventionRead(CausalInterventionCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    created_by_user_id: UUID
    created_at: datetime
    updated_at: datetime


class CausalOutcomeAssessmentCreate(BaseModel):
    intervention_id: UUID
    action_outcome_id: UUID
    hypothesis_effect: CausalOutcomeEffectLiteral
    chain_interrupted: bool = False
    notes: str | None = None
    evidence_summary: str | None = None


class CausalOutcomeAssessmentRead(CausalOutcomeAssessmentCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    assessed_by_user_id: UUID
    assessed_at: datetime
    created_at: datetime
    updated_at: datetime


class RootCauseRankingEntry(BaseModel):
    chain_id: UUID
    chain_code: str
    root_cause_node_id: UUID
    terminal_impact_node_id: UUID
    path_score: Decimal
    weakest_link_confidence: Decimal | None
    occurrence_count: int
    trend_direction: str | None
    total_economic_impact: Decimal | None
    total_operational_impact: Decimal | None
    intervention_coverage: bool


class GraphTraversalRead(BaseModel):
    nodes: list[CausalNodeRead]
    edges: list[CausalEdgeRead]
