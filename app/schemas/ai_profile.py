from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AIOperationalProfileCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: str = Field(min_length=1, max_length=255)


class AIProfileDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["CONFIRM", "CORRECT", "DEFER"]
    corrected_code: str | None = Field(default=None, max_length=150)
    corrected_value: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def correction_requires_value(self) -> "AIProfileDecision":
        if self.decision == "CORRECT" and not (self.corrected_code or self.corrected_value):
            raise ValueError("CORRECT requires corrected_code or corrected_value")
        if self.decision != "CORRECT" and (self.corrected_code or self.corrected_value):
            raise ValueError("corrected values are only accepted for CORRECT")
        return self


class AIProfileInferenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    profile_id: UUID
    sequence_number: int
    inference_type: str
    proposed_code: str | None
    proposed_value: str | None
    display_value: str | None
    confidence: Literal["HIGH", "MEDIUM", "LOW"]
    status: Literal["INFERRED", "CONFIRMED", "CORRECTED", "REJECTED", "DEFERRED", "SUPERSEDED"]
    reasoning_summary: str
    evidence_references: list[str]
    alternative_candidates: list[str]
    confirmed_by_user_id: UUID | None
    confirmed_at: datetime | None
    rejected_by_user_id: UUID | None
    rejected_at: datetime | None
    deferred_by_user_id: UUID | None
    deferred_at: datetime | None
    corrected_code: str | None
    corrected_value: str | None
    created_at: datetime
    updated_at: datetime


class AIOperationalProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    requested_by_user_id: UUID
    idempotency_key: str
    status: Literal["running", "completed", "partial", "failed", "unavailable"]
    provider_code: str
    model_code: str
    model_version: str | None
    template_code: str
    template_version: str
    input_fingerprint: str
    execution_fingerprint: str
    request_hash: str
    response_hash: str | None
    generated_at: datetime
    completed_at: datetime | None
    profile_summary_snapshot: dict[str, object]
    input_provenance_snapshot: dict[str, object]
    observability_snapshot: dict[str, object]
    limitations: list[str]
    failure_code: str | None
    failure_message_sanitized: str | None
    created_at: datetime
    inferences: list[AIProfileInferenceRead] = Field(default_factory=list)
