from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# P3.xxE.1A Semantic Review & Governance Foundation.


class MachineProposalRead(BaseModel):
    model_config = ConfigDict(extra="allow")

    source_field: str
    selected_concept: str | None
    confidence: float
    status: str
    evidence_summary: list[str]
    alternative_candidates: list[dict[str, object]]
    decision_source: str
    decision_version: str
    # P3.xxE.2: structured AI provenance, null for purely deterministic
    # decisions -- see app/models/semantic.py's ai_provenance column.
    ai_provenance: dict[str, object] | None = None


class EffectiveDecisionRead(BaseModel):
    effective_status: str
    effective_concept: str | None
    source: str
    effective_confidence: float | None
    human_validated: bool
    explanation: str


class ReviewQueueItemRead(BaseModel):
    decision_id: UUID
    analysis_case_dataset_id: UUID
    dataset_label: str
    source_field: str
    machine_selected_concept: str | None
    machine_confidence: float
    machine_status: str
    alternative_candidates: list[dict[str, object]]
    evidence_summary: list[str]
    current_version: int | None
    effective_state: str
    group: str


class ReviewQueueRead(BaseModel):
    analysis_case_id: UUID
    run_id: UUID | None
    items: list[ReviewQueueItemRead]


class ReviewItemDetailRead(BaseModel):
    decision_id: UUID
    machine_proposal: MachineProposalRead
    effective_decision: EffectiveDecisionRead
    current_version: int


class SubmitReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str
    corrected_concept: str | None = None
    notes: str | None = Field(default=None, max_length=2000)
    expected_version: int = Field(ge=0)


class SemanticReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    decision_id: UUID
    action: str
    corrected_concept: str | None
    notes: str | None
    reviewer_user_id: UUID
    reviewer_role: str
    reviewed_at: datetime


class SemanticDecisionVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    decision_id: UUID
    version_number: int
    supersedes_version_id: UUID | None
    effective_status: str
    effective_concept: str | None
    source: str
    effective_confidence: float | None
    created_by_user_id: UUID
    created_at: datetime


class SubmitReviewResponse(BaseModel):
    review: SemanticReviewRead
    version: SemanticDecisionVersionRead
    effective_decision: EffectiveDecisionRead


class ReviewHistoryEntryRead(BaseModel):
    review: SemanticReviewRead
    version: SemanticDecisionVersionRead


class ReviewHistoryRead(BaseModel):
    decision_id: UUID
    machine_proposal: MachineProposalRead
    entries: list[ReviewHistoryEntryRead]


class EffectiveFieldRead(BaseModel):
    decision_id: UUID
    analysis_case_dataset_id: UUID
    source_field: str
    effective_decision: EffectiveDecisionRead


class RunEffectiveDecisionsRead(BaseModel):
    analysis_case_id: UUID
    run_id: UUID
    fields: list[EffectiveFieldRead]
