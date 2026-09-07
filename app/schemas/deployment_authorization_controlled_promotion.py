from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class DeploymentAuthorizationRequest(BaseModel):
    approve: bool
    environment: Literal["staging", "production"]
    expected_merge_commit_sha: str = Field(min_length=7, max_length=100)
    note: str | None = Field(default=None, max_length=2000)


class ControlledPromotionStart(BaseModel):
    worker_id: str = Field(min_length=1, max_length=200)
    environment: Literal["staging", "production"]
    expected_merge_commit_sha: str = Field(min_length=7, max_length=100)


class ControlledPromotionComplete(BaseModel):
    lease_id: UUID
    outcome: Literal["deployed", "failed", "escalated"]
    environment: Literal["staging", "production"]
    deployed_commit_sha: str = Field(min_length=7, max_length=100)
    deployment_reference: str | None = Field(default=None, max_length=2000)
    summary: str = Field(min_length=1, max_length=4000)
    escalation_reason: str | None = Field(default=None, max_length=4000)
