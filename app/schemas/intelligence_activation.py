from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CapabilityRead(BaseModel):
    """Read-only projection of an in-code IntelligencePackDefinition --
    never persisted, served directly from the registry (spec's own
    "capabilities" API surface)."""

    pack_code: str
    rule_code: str
    version: str
    required_domains: list[str]
    required_canonical_fields: list[str]
    required_canonical_entities: list[str]
    required_relationships: list[str]
    required_activities: list[str]
    required_states: list[str]
    required_canonical_measures: list[str]
    currency_behavior: str
    unit_behavior: str
    activation_policy_version: str
    is_disabled: bool


class CapabilityListRead(BaseModel):
    capabilities: list[CapabilityRead] = Field(default_factory=list)


class ActivationDecisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    analysis_case_id: UUID
    run_id: UUID
    pack_code: str
    rule_code: str
    pack_version: str
    activation_policy_version: str
    mode: str
    legacy_activated: bool
    legacy_reason: str
    governed_status: str
    governed_missing_summary: list[str]
    governed_confidence_summary: dict[str, object]
    agree: bool
    evidence_summary: list[str]
    created_at: datetime


class ActivationDecisionListRead(BaseModel):
    analysis_case_id: UUID
    run_id: UUID | None
    decisions: list[ActivationDecisionRead] = Field(default_factory=list)


class ShadowComparisonSummaryRead(BaseModel):
    analysis_case_id: UUID
    run_id: UUID | None
    packs_evaluated: int
    agree_count: int
    disagree_count: int
    decisions: list[ActivationDecisionRead] = Field(default_factory=list)
