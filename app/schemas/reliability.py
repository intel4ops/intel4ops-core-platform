from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CensoringStatus(StrEnum):
    FAILURE_OBSERVED = "FAILURE_OBSERVED"
    RIGHT_CENSORED = "RIGHT_CENSORED"
    LEFT_TRUNCATED = "LEFT_TRUNCATED"
    INTERVAL_CENSORED = "INTERVAL_CENSORED"
    UNKNOWN = "UNKNOWN"


class ReliabilityObservationInput(BaseModel):
    asset_reference: str = Field(min_length=1, max_length=255)
    asset_class: str = Field(min_length=1, max_length=100)
    duration: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    exposure: float = Field(default=0, ge=0, allow_inf_nan=False)
    downtime: float = Field(default=0, ge=0, allow_inf_nan=False)
    repair_duration: float = Field(default=0, ge=0, allow_inf_nan=False)
    failure_count: int = Field(default=0, ge=0, strict=True)
    repair_count: int = Field(default=0, ge=0, strict=True)
    event_observed: bool = Field(default=False, strict=True)
    censoring_status: CensoringStatus = CensoringStatus.RIGHT_CENSORED
    lifecycle_state: str = Field(default="ACTIVE", max_length=40)
    normalized_value: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    weight: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def consistent_event(self) -> "ReliabilityObservationInput":
        if self.event_observed != (self.censoring_status == CensoringStatus.FAILURE_OBSERVED):
            raise ValueError("event_observed must agree with censoring_status")
        if self.downtime > self.exposure:
            raise ValueError("downtime cannot exceed exposure")
        return self


class ReliabilityExecutionCreate(BaseModel):
    definition_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]*(?:\.[A-Z][A-Z0-9_]*)+$")
    definition_version: str = Field(default="1.0.0", pattern=r"^[0-9]+(?:\.[0-9]+)*$")
    trust_assessment_id: UUID
    readiness_assessment_id: UUID
    orchestration_request_id: UUID | None = None
    dataset_reference: str = Field(min_length=1, max_length=255)
    dataset_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_lineage_reference: str = Field(min_length=1, max_length=500)
    asset_scope_reference: str = Field(min_length=1, max_length=255)
    asset_scope_type: str = Field(default="ASSET_GROUP", max_length=40)
    method_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    method_version: str = Field(default="1.0")
    observation_window_start: datetime
    observation_window_end: datetime
    exposure_basis: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$", max_length=40)
    exposure_unit: str = Field(min_length=1, max_length=50)
    failure_definition_code: str = Field(min_length=1, max_length=100)
    failure_definition_version: str = Field(default="1.0", max_length=30)
    censoring_policy: str = Field(default="EXPLICIT", max_length=50)
    observations: list[ReliabilityObservationInput] = Field(min_length=1, max_length=10000)
    correlation_id: str = Field(min_length=1, max_length=100)

    @field_validator("observation_window_start", "observation_window_end")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("Observation timestamps must include a timezone")
        return value

    @model_validator(mode="after")
    def valid_window_and_units(self) -> "ReliabilityExecutionCreate":
        if self.observation_window_end <= self.observation_window_start:
            raise ValueError("Observation window end must follow start")
        if len({item.asset_class for item in self.observations}) > 1:
            raise ValueError("Mixed asset classes require governed grouping")
        return self


class ReliabilityEvaluationObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_reference: str | None = Field(default=None, min_length=1, max_length=255)
    asset_class: str | None = Field(default=None, min_length=1, max_length=100)
    duration: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    exposure: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    downtime: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    repair_duration: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    failure_count: int | None = Field(default=None, ge=0, strict=True)
    repair_count: int | None = Field(default=None, ge=0, strict=True)
    event_observed: bool | None = Field(default=None, strict=True)
    normalized_value: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    weight: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def valid_exposure_context(self) -> "ReliabilityEvaluationObservation":
        if (
            self.exposure is not None
            and self.downtime is not None
            and self.downtime > self.exposure
        ):
            raise ValueError("downtime cannot exceed exposure")
        return self


class ReliabilityEvaluateRequest(BaseModel):
    method_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    method_version: str = "1.0"
    observations: list[ReliabilityEvaluationObservation] = Field(min_length=1, max_length=10000)


class ReliabilityEvaluationRead(BaseModel):
    status: str
    method_code: str
    method_version: str
    values: dict[str, float | None]
    diagnostics: dict[str, object]
    limitations: list[str]


class ReliabilityMethodRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    method_code: str
    method_name: str
    method_version: str
    capability_class: str
    supported_exposure_bases: tuple[str, ...]
    supports_censoring: bool
    supports_grouped_assets: bool
    supports_condition_inputs: bool
    supports_uncertainty: bool
    minimum_failure_count: int
    minimum_asset_count: int
    minimum_exposure: float
    supported: bool
    deprecated: bool
    known_limitations: tuple[str, ...]


class ReliabilityExecutionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    asset_scope_reference: str
    asset_scope_type: str
    reliability_method_code: str
    reliability_method_version: str
    status: str
    dataset_reference: str
    exposure_basis: str
    exposure_unit: str
    failure_definition_code: str
    correlation_id: str
    explanation: dict[str, object]
    warnings: list[str]
    limitations: list[str]
    created_at: datetime
    completed_at: datetime | None


class ReliabilityExecutionPage(BaseModel):
    items: list[ReliabilityExecutionRead]
    page: int
    page_size: int
    total: int


class ReliabilityReviewCreate(BaseModel):
    assessment_type: str = Field(min_length=1, max_length=50)
    assessment_reference: str = Field(min_length=1, max_length=255)
    review_status: str = Field(pattern=r"^(APPROVED|REJECTED|NEEDS_INVESTIGATION)$")
    was_actionable: bool
    was_false_positive: bool
    notes: str = Field(default="", max_length=4000)
