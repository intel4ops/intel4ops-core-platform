from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.trust import (
    AnalyticalLevel,
    ReadinessStatus,
    TrustAssessmentStatus,
    TrustDimension,
    TrustEvidenceType,
    TrustExecutionStatus,
    TrustResultStatus,
    TrustRuleSeverity,
)
from app.schemas.raw_lineage import validate_metadata

MAX_ASSESSMENT_RECORDS = 1000
MAX_RULE_CONFIGURATIONS = 50
MAX_EVIDENCE_PAGE_SIZE = 200


class TrustAssessmentCreate(BaseModel):
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=255)
    ingestion_batch_id: UUID | None = None
    industry_pack_code: str | None = Field(
        default=None, min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9._-]*$"
    )
    records: list[dict[str, object]] = Field(
        default_factory=list, max_length=MAX_ASSESSMENT_RECORDS
    )
    rule_configurations: dict[str, dict[str, object]] = Field(
        min_length=1, max_length=MAX_RULE_CONFIGURATIONS
    )
    evaluation_time: datetime | None = None

    @field_validator("records")
    @classmethod
    def safe_records(cls, value: list[dict[str, object]]) -> list[dict[str, object]]:
        for record in value:
            validate_metadata(record)
        return value

    @field_validator("rule_configurations")
    @classmethod
    def safe_configurations(
        cls, value: dict[str, dict[str, object]]
    ) -> dict[str, dict[str, object]]:
        for configuration in value.values():
            validate_metadata(configuration)
        return value

    @field_validator("evaluation_time")
    @classmethod
    def aware_time(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() is None:
            raise ValueError("Evaluation time must include a timezone")
        return value


class DimensionScores(BaseModel):
    completeness: float | None = None
    validity: float | None = None
    consistency: float | None = None
    uniqueness: float | None = None
    timeliness: float | None = None
    lineage: float | None = None


class TrustAssessmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    dataset_id: UUID
    ingestion_batch_id: UUID | None
    industry_pack_code: str | None
    status: TrustAssessmentStatus
    overall_score: float | None
    completeness_score: float | None
    validity_score: float | None
    consistency_score: float | None
    uniqueness_score: float | None
    timeliness_score: float | None
    lineage_score: float | None
    assessed_row_count: int
    passed_rule_count: int
    warning_rule_count: int
    failed_rule_count: int
    skipped_rule_count: int
    started_at: datetime
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TrustRuleResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    trust_assessment_id: UUID
    rule_code: str
    rule_version: str
    rule_name: str
    dimension: TrustDimension
    severity: TrustRuleSeverity
    execution_status: TrustExecutionStatus
    result_status: TrustResultStatus
    checked_record_count: int
    affected_record_count: int
    affected_percentage: float | None
    threshold_definition: dict[str, object]
    observed_value: dict[str, object] | None
    score: float | None
    message: str
    remediation_guidance: str | None
    created_at: datetime


class TrustEvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    trust_rule_result_id: UUID
    dataset_id: UUID
    source_record_identifier: str | None
    canonical_record_identifier: str | None
    field_name: str | None
    observed_value: dict[str, object] | None
    expected_condition: str | None
    evidence_type: TrustEvidenceType
    source_reference: str | None
    created_at: datetime


class PaginatedTrustEvidence(BaseModel):
    items: list[TrustEvidenceRead]
    offset: int
    limit: int
    returned: int
    total: int


class AnalyticalReadinessDecisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    trust_assessment_id: UUID
    analytical_level: AnalyticalLevel
    readiness_status: ReadinessStatus
    blocking_rule_codes: list[str]
    warning_rule_codes: list[str]
    explanation: str
    created_at: datetime
