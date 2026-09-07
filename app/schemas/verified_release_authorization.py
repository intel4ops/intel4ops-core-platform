from __future__ import annotations

from pydantic import BaseModel, Field


class VerifiedReleaseAuthorizationRequest(BaseModel):
    approve: bool
    expected_head_sha: str = Field(min_length=7, max_length=100)
    pull_request_number: int = Field(ge=1)
    note: str | None = Field(default=None, max_length=2000)
