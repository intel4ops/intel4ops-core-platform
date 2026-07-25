from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ExecutionType(StrEnum):
    CALCULATION = "calculation"
    RULE = "rule"


class EvidenceReference(BaseModel):
    raw_record_reference_id: UUID | None = None
    lineage_node_id: UUID | None = None
    canonical_record_identifier: str | None = Field(default=None, max_length=255)
    aggregate_reference: dict[str, object] | None = None
    contributing_record_count: int = Field(default=0, ge=0)
    excluded_record_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def require_reference(self) -> "EvidenceReference":
        if not any(
            (
                self.raw_record_reference_id,
                self.lineage_node_id,
                self.canonical_record_identifier,
                self.aggregate_reference,
            )
        ):
            raise ValueError("At least one evidence reference is required")
        return self


class IntelligenceExecutionCreate(BaseModel):
    dataset_id: UUID
    dataset_version_id: UUID | None = None
    trust_assessment_id: UUID | None = None
    execution_type: ExecutionType
    definition_code: str = Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=100)
    definition_version: str = Field(default="1.0", pattern=r"^[0-9]+(?:\.[0-9]+)*$")
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=255)
    records: list[dict[str, object]] = Field(default_factory=list, max_length=1000)
    parameters: dict[str, object] = Field(default_factory=dict, max_length=30)
    unit: str | None = Field(default=None, max_length=50)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    exposure_value: Decimal | None = None
    exposure_currency: str | None = Field(default=None, min_length=3, max_length=3)
    input_period_start: datetime | None = None
    input_period_end: datetime | None = None
    evaluation_time: datetime | None = None
    evidence: list[EvidenceReference] = Field(default_factory=list, max_length=200)

    @field_validator("currency", "exposure_currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.upper()
        if not value.isascii() or not value.isalpha():
            raise ValueError("Currency must contain three ASCII letters")
        return value

    @field_validator("evaluation_time", "input_period_start", "input_period_end")
    @classmethod
    def aware_datetime(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() is None:
            raise ValueError("Datetime must include a timezone")
        return value

    @model_validator(mode="after")
    def consistent_values(self) -> "IntelligenceExecutionCreate":
        if self.exposure_value is not None and self.exposure_currency is None:
            raise ValueError("Exposure currency is required with exposure value")
        if self.currency and self.exposure_currency and self.currency != self.exposure_currency:
            raise ValueError("Result and exposure currencies must match")
        if (
            self.input_period_start
            and self.input_period_end
            and self.input_period_start > self.input_period_end
        ):
            raise ValueError("Input period start must not exceed end")
        return self


class IntelligenceExecutionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    dataset_id: UUID
    dataset_version_id: UUID | None
    trust_assessment_id: UUID
    readiness_decision_id: UUID
    execution_type: ExecutionType
    definition_code: str
    definition_version: str
    definition_fingerprint: str
    input_fingerprint: str
    status: str
    result_value: Decimal | None
    comparison_value: Decimal | None
    threshold_value: Decimal | None
    unit: str | None
    currency: str | None
    breached: bool | None
    checked_record_count: int
    excluded_record_count: int
    affected_record_count: int
    exposure_value: Decimal | None
    exposure_currency: str | None
    blocking_rule_codes: list[str]
    warning_rule_codes: list[str]
    warnings: list[str]
    limitations: list[str]
    non_execution_reason: str | None
    evaluation_time: datetime
    completed_at: datetime | None
    created_at: datetime
    evidence: list["EvidenceReferenceRead"]


class EvidenceReferenceRead(EvidenceReference):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    execution_id: UUID
    created_at: datetime


class DefinitionRead(BaseModel):
    code: str
    version: str
    name: str
    description: str
    operation: str
    required_parameters: list[str]
    analytical_level: str
    status: str
