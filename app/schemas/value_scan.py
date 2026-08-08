from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DirectionalValueScanCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str = Field(min_length=1, max_length=255)


class DirectionalValueScanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    requested_by_user_id: UUID
    idempotency_key: str
    request_fingerprint: str
    input_fingerprint: str
    ranking_policy_code: str
    ranking_policy_version: str
    status: Literal["completed", "partial", "refused"]
    generated_at: datetime
    candidate_finding_count: int
    opportunity_count: int
    data_gap_count: int
    data_coverage_snapshot: dict[str, object]
    trust_readiness_snapshot: dict[str, object]
    customer_context_snapshot: dict[str, object]
    opportunity_snapshot: list[dict[str, object]]
    data_gap_snapshot: list[dict[str, object]]
    next_investigation_snapshot: dict[str, object] | None
    provenance_snapshot: dict[str, object]
    limitations: list[str]
    result_content_hash: str
    created_at: datetime
    is_current: bool = False
