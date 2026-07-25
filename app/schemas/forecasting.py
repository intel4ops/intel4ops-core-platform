from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ForecastPeriodStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    LATE = "late"
    MISSING = "missing"
    DUPLICATE = "duplicate"
    IRREGULAR = "irregular"


class ForecastObservationInput(BaseModel):
    timestamp: datetime
    value: float | int | None
    status: ForecastPeriodStatus = ForecastPeriodStatus.COMPLETE
    unit: str = Field(min_length=1, max_length=50)
    currency_code: str | None = Field(default=None, min_length=3, max_length=3)
    entity_reference: str | None = Field(default=None, max_length=255)
    confirmed_data_error: bool = False

    @field_validator("timestamp")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("Timestamp must include a timezone")
        return value

    @field_validator("currency_code")
    @classmethod
    def currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.upper()
        if not normalized.isascii() or not normalized.isalpha():
            raise ValueError("Currency must contain three ASCII letters")
        return normalized


class ForecastExecutionCreate(BaseModel):
    definition_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]*(?:\.[A-Z][A-Z0-9_]*)+$")
    definition_version: str = Field(default="1.0.0")
    trust_assessment_id: UUID
    readiness_assessment_id: UUID
    orchestration_request_id: UUID | None = None
    dataset_reference: str = Field(min_length=1, max_length=255)
    dataset_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_lineage_reference: str = Field(min_length=1, max_length=500)
    target_code: str = Field(min_length=1, max_length=150)
    source_time_grain: str = Field(default="MONTHLY", max_length=40)
    forecast_time_grain: str = Field(default="MONTHLY", max_length=40)
    forecast_horizon: int = Field(default=3, ge=1, le=120)
    candidate_methods: list[str] = Field(
        default_factory=lambda: ["NAIVE"], min_length=1, max_length=12
    )
    primary_metric: str = Field(default="WAPE", max_length=40)
    interval_level: float = Field(default=0.8, ge=0.5, le=0.99)
    backtest_type: str = Field(default="ROLLING_ORIGIN", pattern=r"^(HOLDOUT|ROLLING_ORIGIN)$")
    backtest_folds: int = Field(default=3, ge=1, le=20)
    missing_period_policy: str = Field(default="BLOCK")
    partial_period_policy: str = Field(default="EXCLUDE")
    outlier_policy: str = Field(default="KEEP")
    maximum_imputed_percentage: float = Field(default=10, ge=0, le=100)
    parameters: dict[str, object] = Field(default_factory=dict, max_length=40)
    observations: list[ForecastObservationInput] = Field(min_length=2, max_length=10000)
    correlation_id: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def measurement_context(self) -> ForecastExecutionCreate:
        units = {item.unit for item in self.observations}
        currencies = {
            item.currency_code for item in self.observations if item.currency_code is not None
        }
        if len(units) != 1:
            raise ValueError("Forecast observations require one stable unit")
        if len(currencies) > 1:
            raise ValueError("Forecast observations require one stable currency")
        if self.source_time_grain != self.forecast_time_grain:
            raise ValueError("Grain conversion requires a later governed aggregation service")
        return self


class ForecastEvaluateRequest(BaseModel):
    method_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    method_version: str = "1.0"
    values: list[float] = Field(min_length=2, max_length=10000)
    horizon: int = Field(default=3, ge=1, le=120)
    parameters: dict[str, object] = Field(default_factory=dict)


class ForecastMethodRead(BaseModel):
    method_code: str
    method_name: str
    method_version: str
    capability_class: str
    minimum_history: int
    minimum_seasonal_cycles: int
    supports_trend: bool
    supports_seasonality: bool
    supports_exogenous: bool
    supports_intervals: bool
    supports_negative_values: bool
    supports_zero_values: bool
    supports_intermittent_demand: bool
    complexity_rank: int
    supported: bool


class ForecastEvaluationRead(BaseModel):
    status: str
    method_code: str
    method_version: str
    values: list[float]
    intervals: list[dict[str, float | None]]
    diagnostics: dict[str, object]
    error_code: str | None = None


class ForecastExecutionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    target_code: str
    target_unit: str
    currency_code: str | None
    source_time_grain: str
    forecast_time_grain: str
    status: str
    dataset_reference: str
    dataset_fingerprint: str
    prepared_series_fingerprint: str
    forecast_horizon: int
    selected_method_code: str | None
    selected_method_version: str | None
    correlation_id: str
    readiness_snapshot: dict[str, object]
    explanation: dict[str, object]
    warnings: list[str]
    limitations: list[str]
    created_at: datetime
    completed_at: datetime | None


class ForecastCandidateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    method_code: str
    method_version: str
    status: str
    eligible: bool
    rejection_reason: str | None
    primary_metric_code: str
    primary_metric_value: float | None
    secondary_metrics: dict[str, object]
    bias_value: float | None
    interval_coverage: float | None
    selected: bool
    selection_rank: int | None
    selection_rationale: str | None


class ForecastPointRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    entity_reference: str | None
    scenario_code: str
    forecast_period_start: datetime
    forecast_period_end: datetime
    horizon_step: int
    point_forecast: float
    lower_bound: float | None
    upper_bound: float | None
    interval_level: float | None
    output_unit: str
    currency_code: str | None
    assumptions: list[str]


class ForecastExecutionPage(BaseModel):
    items: list[ForecastExecutionRead]
    page: int
    page_size: int
    total: int


class ForecastScenarioCreate(BaseModel):
    scenario_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$", max_length=50)
    name: str = Field(min_length=1, max_length=150)
    description: str = Field(min_length=1, max_length=2000)
    adjustment_type: str = Field(pattern=r"^(PERCENTAGE|ADDITIVE)$")
    adjustment_amount: float
    effective_from: datetime
    effective_to: datetime


class ForecastScenarioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    scenario_code: str
    name: str
    adjustment_type: str
    adjustment_parameters: dict[str, object]
    created_at: datetime


class ForecastActualCreate(BaseModel):
    actual_reference: str = Field(min_length=1, max_length=500)
    actual_value: float
    actual_dataset_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")


class ForecastActualRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    forecast_point_id: UUID
    actual_reference: str
    actual_value: float | None
    actual_status: str
    evaluated_at: datetime | None


class ForecastRevisionCreate(BaseModel):
    revised_execution_id: UUID
    revision_reason: str = Field(min_length=1, max_length=2000)
    revision_type: str = Field(default="DATA_UPDATE", max_length=50)
