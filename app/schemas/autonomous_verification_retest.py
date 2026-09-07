from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class VerificationRetestStart(BaseModel):
    worker_id: str = Field(min_length=1, max_length=200)


class VerificationSimulationResult(BaseModel):
    simulation_id: str = Field(min_length=1, max_length=200)
    true_positive_count: int = Field(ge=0)
    false_positive_count: int = Field(ge=0)
    false_negative_count: int = Field(ge=0)


class VerificationRetestComplete(BaseModel):
    lease_id: UUID
    outcome: Literal["scored", "failed", "escalated"]
    candidate_head_sha: str = Field(min_length=7, max_length=100)
    pull_request_number: int = Field(ge=1)
    results: list[VerificationSimulationResult] = Field(default_factory=list, max_length=500)
    summary: str = Field(min_length=1, max_length=4000)
    escalation_reason: str | None = Field(default=None, max_length=2000)
