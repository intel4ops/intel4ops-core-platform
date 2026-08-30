from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class FieldProfileRead(BaseModel):
    model_config = ConfigDict(extra="allow")

    source_field: str
    physical_type: str
    null_rate: float
    uniqueness_ratio: float
    distinct_count: int
    sample_values: list[str] = Field(default_factory=list)
    value_patterns: list[str] = Field(default_factory=list)
    is_candidate_identifier: bool = False
    is_candidate_categorical: bool = False
    is_currency_like: bool = False


class DatasetProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    dataset_label: str
    row_count: int
    column_count: int
    field_profiles: list[dict[str, object]]
    computed_at: datetime


class RoleInterpretationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    primary_role: str
    confidence: float
    evidence: list[str]
    secondary_roles: list[str]
    alternative_roles: list[dict[str, object]]
    computed_at: datetime


class SemanticCandidateRead(BaseModel):
    model_config = ConfigDict(extra="allow")

    candidate_concept: str
    confidence: float
    candidate_rank: int
    generated_by: str
    evidence_components: list[dict[str, object]] = Field(default_factory=list)


class FieldInterpretationDecisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_field: str
    selected_concept: str | None
    confidence: float
    status: str
    evidence_summary: list[str]
    alternative_candidates: list[dict[str, object]]
    decision_source: str
    decision_version: str
    # P3.xxE.2: structured AI provenance ({"ai_used": true, "provider_code":
    # ..., "model_version": ...}), null for purely deterministic decisions.
    ai_provenance: dict[str, object] | None
    review_actor_user_id: UUID | None
    review_timestamp: datetime | None


class DatasetSemanticRead(BaseModel):
    analysis_case_dataset_id: UUID
    dataset_id: UUID
    source_label: str
    profile: DatasetProfileRead | None
    role: RoleInterpretationRead | None
    field_decisions: list[FieldInterpretationDecisionRead] = Field(default_factory=list)


class AnalysisCaseSemanticRead(BaseModel):
    analysis_case_id: UUID
    run_id: UUID | None
    datasets: list[DatasetSemanticRead] = Field(default_factory=list)
