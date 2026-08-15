from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.recovery_workspace import RecoveryWorkspaceRead

LearningType = Literal[
    "operational_pattern",
    "corrective_action",
    "causal_observation",
    "execution_playbook",
    "risk_indicator",
    "verification_pattern",
]
LearningStatus = Literal["candidate", "reviewed", "approved_for_reuse", "rejected", "retired"]
ProvenanceType = Literal["production", "simulation", "manual", "mixed"]
ValueBasis = Literal["none", "expected", "realized_measurement", "verified_ledger"]


class MemoryFindingRead(BaseModel):
    id: UUID
    title: str
    summary: str
    status: str
    finding_type: str | None
    domain: str
    confidence_score: float
    exposure_value: str | None
    exposure_currency: str | None
    causal_chain_id: str | None
    created_at: datetime


class MemoryEvidenceRead(BaseModel):
    id: UUID
    evidence_type: str
    source_type: str
    source_identifier: str
    observed_at: datetime | None
    created_at: datetime


class LearningEligibilityRead(BaseModel):
    eligible: bool
    reasons: list[str]
    has_outcome: bool
    has_realized_value: bool
    has_verified_value: bool
    provenance_type: ProvenanceType


class LearningSourceCaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    finding_id: UUID
    provenance_type: ProvenanceType


class LearningAuditRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    event_type: str
    prior_status: str | None
    new_status: str
    actor_user_id: UUID
    actor_role: str
    rationale: str | None
    occurred_at: datetime


class LearningRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    learning_type: LearningType
    title: str
    statement: str
    scope: str
    status: LearningStatus
    provenance_type: ProvenanceType
    value_basis: ValueBasis
    rationale: str | None
    created_by_user_id: UUID
    reviewed_by_user_id: UUID | None
    created_at: datetime
    reviewed_at: datetime | None
    updated_at: datetime
    source_cases: list[LearningSourceCaseRead] = []
    audit_history: list[LearningAuditRead] = []


class OperationalMemoryRead(BaseModel):
    organization_id: UUID
    finding: MemoryFindingRead
    finding_evidence: list[MemoryEvidenceRead]
    recovery_workspace: RecoveryWorkspaceRead
    eligibility: LearningEligibilityRead
    learnings: list[LearningRead]


class LearningCreate(BaseModel):
    learning_type: LearningType
    title: str = Field(min_length=1, max_length=250)
    statement: str = Field(min_length=1, max_length=5000)
    scope: str = Field(min_length=1, max_length=2000)
    source_finding_ids: list[UUID] = Field(min_length=1, max_length=20)
    value_basis: ValueBasis = "none"


class LearningTransition(BaseModel):
    transition: Literal["review", "approve", "reject", "retire"]
    rationale: str = Field(min_length=1, max_length=2000)


class LearningPage(BaseModel):
    items: list[LearningRead]
    page: int
    page_size: int
    total: int
