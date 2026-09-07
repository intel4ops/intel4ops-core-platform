from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class GovernedMergeStart(BaseModel):
    worker_id: str = Field(min_length=1, max_length=200)


class GovernedMergeComplete(BaseModel):
    lease_id: UUID
    outcome: Literal["merged", "failed", "escalated"]
    candidate_head_sha: str = Field(min_length=7, max_length=100)
    pull_request_number: int = Field(ge=1)
    target_branch: str = Field(default="main", min_length=1, max_length=200)
    merge_commit_sha: str | None = Field(default=None, min_length=7, max_length=100)
    summary: str = Field(min_length=1, max_length=4000)
    escalation_reason: str | None = Field(default=None, max_length=2000)
