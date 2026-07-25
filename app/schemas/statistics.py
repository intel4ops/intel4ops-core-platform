from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.statistics import (
    AnomalyDirection,
    AnomalySeverity,
    StatisticalExecutionStatus,
)


class PeriodStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    LATE = "late"
    MISSING = "missing"
    DUPLICATE = "duplicate"
    IRREGULAR = "irregular"


class StatisticalObservationInput(BaseModel):
    value: float | int | None
    entity_reference: str | None = Field(default=None, max_length=255)
    period_reference: str | None = Field(default=None, max_length=100)
    timestamp: datetime | None = None
    period_status: PeriodStatus = PeriodStatus.COMPLETE
    unit: str | None = Field(default=None, max_length=50)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    materiality: float = Field(default=0.5, ge=0, le=1)
    known_event: bool = False
    planned_maintenance: bool = False
    approved_business_event: bool = False

    @field_validator("timestamp")
    @classmethod
    def aware_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() is None:
            raise ValueError("Timestamp must include a timezone")
        return value

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.upper()
        if not value.isascii() or not value.isalpha():
            raise ValueError("Currency must contain three ASCII letters")
        return value


class StatisticalExecutionCreate(BaseModel):
    definition_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]*(?:\.[A-Z][A-Z0-9_]*)+$", max_length=150)
    definition_version: str = Field(default="1.0.0", pattern=r"^[0-9]+(?:\.[0-9]+)*$")
    trust_assessment_id: UUID
    readiness_assessment_id: UUID
    orchestration_request_id: UUID | None = None
    dataset_reference: str = Field(min_length=1, max_length=255)
    dataset_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_lineage_reference: str = Field(min_length=1, max_length=500)
    observations: list[StatisticalObservationInput] = Field(min_length=1, max_length=1000)
    parameters: dict[str, object] = Field(default_factory=dict, max_length=40)
    correlation_id: str = Field(min_length=1, max_length=100)
    idempotency_key: str = Field(min_length=1, max_length=255)
    industry_pack_code: str | None = Field(default=None, max_length=100)
    region_code: str | None = Field(default=None, max_length=30)

    @model_validator(mode="after")
    def consistent_measurement_context(self) -> StatisticalExecutionCreate:
        units = {item.unit for item in self.observations if item.unit is not None}
        currencies = {item.currency for item in self.observations if item.currency is not None}
        if len(units) > 1:
            raise ValueError("Mixed units are not eligible for statistical execution")
        if len(currencies) > 1:
            raise ValueError("Mixed currencies are not eligible for statistical execution")
        return self


class StatisticalEvaluateRequest(BaseModel):
    method_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$", max_length=100)
    method_version: str = Field(default="1.0", pattern=r"^[0-9]+(?:\.[0-9]+)*$")
    values: list[float | int | None] = Field(min_length=1, max_length=1000)
    parameters: dict[str, object] = Field(default_factory=dict, max_length=40)


class StatisticalMethodRead(BaseModel):
    method_code: str
    method_name: str
    method_version: str
    capability_class: str
    minimum_sample_size: int
    supports_time_series: bool
    supports_peer_group: bool
    supports_grouping: bool
    supports_weights: bool


class StatisticalEvaluationRead(BaseModel):
    status: StatisticalExecutionStatus
    method: StatisticalMethodRead
    observed_value: float | None
    expected_value: float | None
    normalized_deviation: float | None
    is_anomaly: bool | None
    threshold: float | None
    summary: dict[str, object]
    error_code: str | None = None
    explanation: str


class ScoreComponentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    component_code: str
    raw_value: float
    normalized_value: float
    weight: float
    contribution: float
    explanation: str


class StatisticalObservationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    statistical_execution_id: UUID
    entity_reference: str | None
    period_reference: str | None
    observed_value: float
    expected_value: float | None
    absolute_deviation: float | None
    relative_deviation: float | None
    normalized_deviation: float | None
    statistical_score: float
    confidence_score: float
    materiality_score: float
    anomaly_direction: AnomalyDirection
    severity: AnomalySeverity
    is_anomaly: bool
    persistence_count: int
    recurrence_count: int
    method_trace: dict[str, object]
    explanation: dict[str, object]
    limitations: list[str]
    evidence_references: list[dict[str, object]]
    score_components: list[ScoreComponentRead] = Field(default_factory=list)
    created_at: datetime


class StatisticalBaselineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    statistical_execution_id: UUID
    baseline_type: str
    baseline_scope: dict[str, object]
    population_definition: dict[str, object]
    time_window_start: datetime | None
    time_window_end: datetime | None
    record_count: int
    entity_count: int
    mean_value: float | None
    median_value: float | None
    minimum_value: float | None
    maximum_value: float | None
    variance_value: float | None
    standard_deviation_value: float | None
    mad_value: float | None
    percentile_values: dict[str, object]
    baseline_fingerprint: str
    limitations: list[str]
    created_at: datetime


class StatisticalExecutionStepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sequence_number: int
    step_code: str
    status: str
    started_at: datetime
    completed_at: datetime | None
    input_summary: dict[str, object]
    output_summary: dict[str, object]
    warning_code: str | None
    error_code: str | None
    explanation: str


class StatisticalExecutionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    orchestration_request_id: UUID | None
    oikb_definition_id: UUID
    oikb_definition_version_id: UUID
    execution_package_fingerprint: str
    reproducibility_fingerprint: str
    method_code: str
    method_version: str
    analytical_level: str
    status: StatisticalExecutionStatus
    requested_by: UUID
    requested_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    blocked_reason: str | None
    failure_code: str | None
    failure_message: str | None
    trust_assessment_id: UUID
    readiness_assessment_id: UUID
    dataset_reference: str
    dataset_fingerprint: str
    source_lineage_reference: str
    parameter_snapshot: dict[str, object]
    engine_version: str
    correlation_id: str
    warnings: list[str]
    limitations: list[str]
    created_at: datetime
    updated_at: datetime


class StatisticalExecutionDetail(StatisticalExecutionRead):
    baselines: list[StatisticalBaselineRead]
    observations: list[StatisticalObservationRead]
    steps: list[StatisticalExecutionStepRead]


class StatisticalExecutionPage(BaseModel):
    items: list[StatisticalExecutionRead]
    page: int
    page_size: int
    total: int


class ObservationReviewCreate(BaseModel):
    review_status: str = Field(pattern=r"^[a-z][a-z_]*$", max_length=30)
    classification: str = Field(pattern=r"^[a-z][a-z_]*$", max_length=50)
    was_actionable: bool
    was_false_positive: bool
    confirmed_cause: str | None = Field(default=None, max_length=2000)
    notes: str = Field(min_length=1, max_length=4000)


class ObservationReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    statistical_observation_id: UUID
    review_status: str
    reviewer_id: UUID
    classification: str
    was_actionable: bool
    was_false_positive: bool
    confirmed_cause: str | None
    notes: str
    reviewed_at: datetime


class ObservationSuppressionCreate(BaseModel):
    suppression_reason: str = Field(min_length=1, max_length=2000)
    suppression_scope: dict[str, object] = Field(default_factory=dict, max_length=20)
    effective_from: datetime
    effective_to: datetime | None = None

    @model_validator(mode="after")
    def valid_window(self) -> ObservationSuppressionCreate:
        if self.effective_from.utcoffset() is None:
            raise ValueError("Suppression start must include a timezone")
        if self.effective_to is not None:
            if self.effective_to.utcoffset() is None:
                raise ValueError("Suppression end must include a timezone")
            if self.effective_to <= self.effective_from:
                raise ValueError("Suppression end must be after start")
        return self


class ObservationSuppressionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    definition_version_id: UUID
    entity_reference: str | None
    suppression_reason: str
    suppression_scope: dict[str, object]
    effective_from: datetime
    effective_to: datetime | None
    created_by: UUID
    created_at: datetime
