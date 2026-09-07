from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class PremiumCodexExecutionStart(BaseModel):
    worker_id: str = Field(min_length=1, max_length=200)


class PremiumCodexExecutionComplete(BaseModel):
    lease_id: UUID
    outcome: Literal["succeeded", "failed", "escalated"]
    branch_name: str | None = Field(default=None, max_length=300)
    head_sha: str | None = Field(default=None, max_length=100)
    pull_request_number: int | None = Field(default=None, ge=1)
    pull_request_url: str | None = Field(default=None, max_length=1000)
    changed_files: list[str] = Field(default_factory=list, max_length=200)
    tests_run: list[str] = Field(default_factory=list, max_length=200)
    summary: str = Field(min_length=1, max_length=4000)
    escalation_reason: str | None = Field(default=None, max_length=2000)
