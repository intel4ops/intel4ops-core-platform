from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AnalysisCaseModeSchema(StrEnum):
    SINGLE = "single"
    ORCHESTRATED = "orchestrated"


class AnalysisCaseActionStatusSchema(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class RecoveryStatusSchema(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    AWAITING_VERIFICATION = "awaiting_verification"
    VERIFIED = "verified"
    NOT_VERIFIED = "not_verified"


class AnalysisCaseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    mode: AnalysisCaseModeSchema
    industry_code: str | None = Field(default=None, max_length=60)
    business_model: str | None = Field(default=None, max_length=60)
    operating_context: str | None = Field(default=None, max_length=200)
    case_currency_hint: str | None = Field(default=None, min_length=3, max_length=3)
    idempotency_key: str | None = Field(default=None, max_length=255)


class AnalysisCaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    case_code: str
    name: str
    mode: str
    status: str
    industry_code: str | None
    business_model: str | None
    operating_context: str | None
    case_currency_hint: str | None
    created_by_user_id: UUID
    created_at: datetime
    updated_at: datetime


class AnalysisCaseRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    analysis_case_id: UUID
    run_number: int
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    heartbeat_at: datetime | None
    error_summary: str | None
    orchestration_version: str
    created_at: datetime


class AnalysisCaseDatasetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dataset_id: UUID
    source_label: str
    detected_domain: str | None
    detection_basis: list[str]
    detection_status: str
    trust_status: str | None
    mapping_status: str | None
    intelligence_readiness_status: str | None
    row_count: int | None


class AnalysisCaseFindingRead(BaseModel):
    finding_id: UUID
    rule_id: str | None
    title: str
    summary: str
    severity: str | None
    confidence_level: str | None
    affected_record_count: int
    economic_status: str | None
    currency_status: str | None
    entities: list[dict[str, object]] | None
    domains: list[str] | None
    observed_values_by_currency: dict[str, float]


class AnalysisCaseActionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding_ids: list[UUID] = Field(min_length=1, max_length=50)
    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    owner: str | None = Field(default=None, max_length=200)
    priority: str | None = Field(default=None, max_length=20)
    due_date: datetime | None = None


class AnalysisCaseActionStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AnalysisCaseActionStatusSchema
    owner: str | None = Field(default=None, max_length=200)


class AnalysisCaseActionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    analysis_case_id: UUID
    title: str
    description: str | None
    owner: str | None
    priority: str | None
    status: str
    due_date: datetime | None
    created_by_user_id: UUID
    created_at: datetime
    updated_at: datetime


class AnalysisCaseRecoveryUpsert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding_id: UUID
    baseline_condition: str | None = None
    intervention_summary: str | None = None
    recovery_status: RecoveryStatusSchema
    observed_post_condition: dict[str, object] | None = None
    observed_value: float | None = None
    estimated_value: float | None = None
    verified_value: float | None = None
    currency_detail: dict[str, object] | None = None
    evidence_json: dict[str, object] | None = None


class AnalysisCaseRecoveryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    analysis_case_id: UUID
    action_id: UUID
    finding_id: UUID
    baseline_condition: str | None
    intervention_summary: str | None
    recovery_status: str
    observed_post_condition: dict[str, object] | None
    observed_value: float | None
    estimated_value: float | None
    verified_value: float | None
    currency_detail: dict[str, object] | None
    evidence_json: dict[str, object] | None
    created_at: datetime
    updated_at: datetime
