from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.narrative.claim_policy import ClaimConfidence, ClaimType


class NarrativeClaimDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_type: ClaimType
    wording: str = Field(min_length=1, max_length=500)
    source_reference_ids: list[str] = Field(min_length=1, max_length=10)
    evidence_reference_ids: list[str] = Field(default_factory=list, max_length=10)
    confidence: ClaimConfidence = ClaimConfidence.NOT_ASSESSED
    limitations: list[str] = Field(default_factory=list, max_length=3)
    value_reference_ids: list[str] = Field(default_factory=list, max_length=5)


class NarrativeOpportunityDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    opportunity_reference_id: str
    narrative: NarrativeClaimDraft


class StructuredNarrativeDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization_id: UUID
    scan_id: UUID
    audience: Literal["EXECUTIVE"] = "EXECUTIVE"
    headline: NarrativeClaimDraft
    executive_summary: list[NarrativeClaimDraft] = Field(max_length=3)
    key_messages: list[NarrativeClaimDraft] = Field(default_factory=list, max_length=5)
    opportunities: list[NarrativeOpportunityDraft] = Field(default_factory=list, max_length=5)
    context_summary: list[NarrativeClaimDraft] = Field(default_factory=list, max_length=3)
    limitations: list[NarrativeClaimDraft] = Field(default_factory=list, max_length=5)
    data_gaps: list[NarrativeClaimDraft] = Field(default_factory=list, max_length=5)
    recommended_next_step: NarrativeClaimDraft | None = None
    provider_limitations: list[str] = Field(default_factory=list, max_length=5)


class NarrativeValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference_id: str
    classification: Literal["POTENTIAL_EXPOSURE"]
    value: dict[str, object]


class NarrativeClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str
    claim_type: ClaimType
    text: str
    source_reference_ids: list[str]
    evidence_reference_ids: list[str]
    confidence: ClaimConfidence
    confidence_language: str
    limitations: list[str]
    governed_values: list[NarrativeValue] = Field(default_factory=list)


class NarrativeOpportunity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    opportunity_reference_id: str
    narrative: NarrativeClaim


class StructuredNarrative(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization_id: UUID
    scan_id: UUID
    audience: Literal["EXECUTIVE"]
    headline: NarrativeClaim
    executive_summary: list[NarrativeClaim]
    key_messages: list[NarrativeClaim]
    opportunities: list[NarrativeOpportunity]
    context_summary: list[NarrativeClaim]
    limitations: list[NarrativeClaim]
    data_gaps: list[NarrativeClaim]
    recommended_next_step: NarrativeClaim | None
    provider_limitations: list[str]


class ExecutiveNarrativeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scan_id: UUID
    profile_id: UUID | None = None
    audience: Literal["EXECUTIVE"] = "EXECUTIVE"
    idempotency_key: str = Field(min_length=1, max_length=255)


class GroundedExecutiveNarrativeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    scan_id: UUID
    profile_id: UUID | None
    requested_by_user_id: UUID
    idempotency_key: str
    audience: Literal["EXECUTIVE"]
    status: Literal["completed", "fallback"]
    provider_code: str | None
    model_code: str | None
    model_version: str | None
    template_code: str
    template_version: str
    schema_version: str
    request_hash: str
    input_fingerprint: str
    execution_fingerprint: str
    source_scan_content_hash: str
    source_profile_fingerprint: str | None
    structured_source_snapshot: dict[str, object]
    structured_narrative_snapshot: dict[str, object]
    limitations: list[str]
    observability_snapshot: dict[str, object]
    provider_failure_code: str | None
    content_hash: str
    generated_at: datetime
    created_at: datetime


class GroundedExecutiveNarrativeList(BaseModel):
    items: list[GroundedExecutiveNarrativeRead]
