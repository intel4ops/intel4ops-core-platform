from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.entities import utc_now
from app.models.source_system import enum_values, portable_json


class ForecastExecutionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    BLOCKED = "blocked"
    NOT_READY = "not_ready"
    INSUFFICIENT_HISTORY = "insufficient_history"
    INSUFFICIENT_SEASONAL_CYCLES = "insufficient_seasonal_cycles"
    INVALID_TIME_SERIES = "invalid_time_series"
    UNSUPPORTED = "unsupported"
    BACKTEST_FAILED = "backtest_failed"
    MODEL_SELECTION_FAILED = "model_selection_failed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ForecastExecution(Base):
    __tablename__ = "forecast_executions"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "reproducibility_fingerprint", name="uq_forecast_reproducibility"
        ),
        CheckConstraint(
            f"status IN ({enum_values(ForecastExecutionStatus)})",
            name="ck_forecast_execution_status",
        ),
        Index("ix_forecast_execution_org_status", "organization_id", "status"),
        Index("ix_forecast_execution_definition", "oikb_definition_version_id"),
        Index("ix_forecast_execution_dataset", "organization_id", "dataset_reference"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    orchestration_request_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("intelligence_orchestration_requests.id", ondelete="SET NULL"), nullable=True
    )
    oikb_definition_id: Mapped[UUID] = mapped_column(
        ForeignKey("oikb_definitions.id", ondelete="RESTRICT")
    )
    oikb_definition_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("oikb_definition_versions.id", ondelete="RESTRICT")
    )
    trust_assessment_id: Mapped[UUID] = mapped_column(
        ForeignKey("trust_assessments.id", ondelete="RESTRICT")
    )
    readiness_assessment_id: Mapped[UUID] = mapped_column(
        ForeignKey("analytical_readiness_decisions.id", ondelete="RESTRICT")
    )
    execution_package_fingerprint: Mapped[str] = mapped_column(String(64))
    reproducibility_fingerprint: Mapped[str] = mapped_column(String(64))
    target_code: Mapped[str] = mapped_column(String(150))
    target_unit: Mapped[str] = mapped_column(String(50))
    currency_code: Mapped[str | None] = mapped_column(String(3), nullable=True)
    source_time_grain: Mapped[str] = mapped_column(String(40))
    forecast_time_grain: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(40))
    requested_by: Mapped[UUID] = mapped_column(Uuid)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dataset_reference: Mapped[str] = mapped_column(String(255))
    dataset_fingerprint: Mapped[str] = mapped_column(String(64))
    prepared_series_fingerprint: Mapped[str] = mapped_column(String(64))
    source_lineage_reference: Mapped[str] = mapped_column(String(500))
    training_window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    training_window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    forecast_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    forecast_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    forecast_horizon: Mapped[int] = mapped_column(Integer)
    selected_method_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    selected_method_version: Mapped[str | None] = mapped_column(String(30), nullable=True)
    engine_version: Mapped[str] = mapped_column(String(30))
    correlation_id: Mapped[str] = mapped_column(String(100))
    readiness_snapshot: Mapped[dict[str, object]] = mapped_column(portable_json)
    explanation: Mapped[dict[str, object]] = mapped_column(portable_json)
    warnings: Mapped[list[str]] = mapped_column(portable_json, default=list)
    limitations: Mapped[list[str]] = mapped_column(portable_json, default=list)
    failure_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    candidates: Mapped[list[ForecastCandidate]] = relationship(cascade="all, delete-orphan")
    points: Mapped[list[ForecastPoint]] = relationship(cascade="all, delete-orphan")
    steps: Mapped[list[ForecastExecutionStep]] = relationship(cascade="all, delete-orphan")


class ForecastCandidate(Base):
    __tablename__ = "forecast_candidates"
    __table_args__ = (
        UniqueConstraint(
            "forecast_execution_id", "method_code", "method_version", name="uq_forecast_candidate"
        ),
        Index("ix_forecast_candidate_execution", "forecast_execution_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    forecast_execution_id: Mapped[UUID] = mapped_column(
        ForeignKey("forecast_executions.id", ondelete="CASCADE")
    )
    method_code: Mapped[str] = mapped_column(String(100))
    method_version: Mapped[str] = mapped_column(String(30))
    parameter_snapshot: Mapped[dict[str, object]] = mapped_column(portable_json)
    status: Mapped[str] = mapped_column(String(40))
    eligible: Mapped[bool] = mapped_column(Boolean)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    primary_metric_code: Mapped[str] = mapped_column(String(40))
    primary_metric_value: Mapped[float | None] = mapped_column(Numeric(38, 12), nullable=True)
    secondary_metrics: Mapped[dict[str, object]] = mapped_column(portable_json)
    bias_value: Mapped[float | None] = mapped_column(Numeric(38, 12), nullable=True)
    interval_coverage: Mapped[float | None] = mapped_column(Numeric(8, 5), nullable=True)
    complexity_rank: Mapped[int] = mapped_column(Integer)
    selected: Mapped[bool] = mapped_column(Boolean, default=False)
    selection_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    selection_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ForecastBacktest(Base):
    __tablename__ = "forecast_backtests"
    __table_args__ = (
        Index("ix_forecast_backtest_execution_fold", "forecast_execution_id", "fold_number"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    forecast_execution_id: Mapped[UUID] = mapped_column(
        ForeignKey("forecast_executions.id", ondelete="CASCADE")
    )
    forecast_candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("forecast_candidates.id", ondelete="CASCADE")
    )
    backtest_type: Mapped[str] = mapped_column(String(30))
    fold_number: Mapped[int] = mapped_column(Integer)
    train_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    train_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    forecast_origin: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    forecast_period: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    horizon_step: Mapped[int] = mapped_column(Integer)
    actual_value: Mapped[float | None] = mapped_column(Numeric(38, 12), nullable=True)
    forecast_value: Mapped[float] = mapped_column(Numeric(38, 12))
    lower_bound: Mapped[float | None] = mapped_column(Numeric(38, 12), nullable=True)
    upper_bound: Mapped[float | None] = mapped_column(Numeric(38, 12), nullable=True)
    error_value: Mapped[float | None] = mapped_column(Numeric(38, 12), nullable=True)
    absolute_error: Mapped[float | None] = mapped_column(Numeric(38, 12), nullable=True)
    percentage_error: Mapped[float | None] = mapped_column(Numeric(38, 12), nullable=True)
    interval_contains_actual: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ForecastMetric(Base):
    __tablename__ = "forecast_metrics"
    __table_args__ = (Index("ix_forecast_metric_execution", "forecast_execution_id"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    forecast_execution_id: Mapped[UUID] = mapped_column(
        ForeignKey("forecast_executions.id", ondelete="CASCADE")
    )
    forecast_candidate_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("forecast_candidates.id", ondelete="CASCADE"), nullable=True
    )
    metric_code: Mapped[str] = mapped_column(String(40))
    metric_value: Mapped[float | None] = mapped_column(Numeric(38, 12), nullable=True)
    horizon_step: Mapped[int | None] = mapped_column(Integer, nullable=True)
    segment_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    valid: Mapped[bool] = mapped_column(Boolean)
    invalid_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ForecastPoint(Base):
    __tablename__ = "forecast_points"
    __table_args__ = (
        UniqueConstraint(
            "forecast_execution_id",
            "scenario_code",
            "horizon_step",
            "entity_reference",
            name="uq_forecast_point",
        ),
        Index("ix_forecast_point_org_period", "organization_id", "forecast_period_start"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    forecast_execution_id: Mapped[UUID] = mapped_column(
        ForeignKey("forecast_executions.id", ondelete="CASCADE")
    )
    entity_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    scenario_code: Mapped[str] = mapped_column(String(50), default="BASE")
    forecast_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    forecast_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    horizon_step: Mapped[int] = mapped_column(Integer)
    point_forecast: Mapped[float] = mapped_column(Numeric(38, 12))
    lower_bound: Mapped[float | None] = mapped_column(Numeric(38, 12), nullable=True)
    upper_bound: Mapped[float | None] = mapped_column(Numeric(38, 12), nullable=True)
    interval_level: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    output_unit: Mapped[str] = mapped_column(String(50))
    currency_code: Mapped[str | None] = mapped_column(String(3), nullable=True)
    is_partial_period: Mapped[bool] = mapped_column(Boolean, default=False)
    assumptions: Mapped[list[str]] = mapped_column(portable_json, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ForecastScenario(Base):
    __tablename__ = "forecast_scenarios"
    __table_args__ = (
        UniqueConstraint("forecast_execution_id", "scenario_code", name="uq_forecast_scenario"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    forecast_execution_id: Mapped[UUID] = mapped_column(
        ForeignKey("forecast_executions.id", ondelete="CASCADE")
    )
    scenario_code: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str] = mapped_column(Text)
    adjustment_type: Mapped[str] = mapped_column(String(40))
    adjustment_parameters: Mapped[dict[str, object]] = mapped_column(portable_json)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    effective_to: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[UUID] = mapped_column(Uuid)
    approved_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ForecastRevision(Base):
    __tablename__ = "forecast_revisions"
    __table_args__ = (
        Index("ix_forecast_revision_org_prior", "organization_id", "prior_forecast_execution_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    prior_forecast_execution_id: Mapped[UUID] = mapped_column(
        ForeignKey("forecast_executions.id", ondelete="RESTRICT")
    )
    revised_forecast_execution_id: Mapped[UUID] = mapped_column(
        ForeignKey("forecast_executions.id", ondelete="RESTRICT")
    )
    revision_reason: Mapped[str] = mapped_column(Text)
    revision_type: Mapped[str] = mapped_column(String(50))
    absolute_revision: Mapped[float | None] = mapped_column(Numeric(38, 12), nullable=True)
    percentage_revision: Mapped[float | None] = mapped_column(Numeric(38, 12), nullable=True)
    method_changed: Mapped[bool] = mapped_column(Boolean, default=False)
    parameters_changed: Mapped[bool] = mapped_column(Boolean, default=False)
    data_changed: Mapped[bool] = mapped_column(Boolean, default=False)
    readiness_changed: Mapped[bool] = mapped_column(Boolean, default=False)
    scenario_changed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ForecastActual(Base):
    __tablename__ = "forecast_actuals"
    __table_args__ = (
        UniqueConstraint("organization_id", "forecast_point_id", name="uq_forecast_actual_point"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    forecast_point_id: Mapped[UUID] = mapped_column(
        ForeignKey("forecast_points.id", ondelete="RESTRICT")
    )
    actual_reference: Mapped[str] = mapped_column(String(500))
    actual_value: Mapped[float | None] = mapped_column(Numeric(38, 12), nullable=True)
    actual_status: Mapped[str] = mapped_column(String(30))
    actual_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actual_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actual_dataset_fingerprint: Mapped[str] = mapped_column(String(64))
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class ForecastAccuracyResult(Base):
    __tablename__ = "forecast_accuracy_results"
    __table_args__ = (
        Index("ix_forecast_accuracy_org_execution", "organization_id", "forecast_execution_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    forecast_execution_id: Mapped[UUID] = mapped_column(
        ForeignKey("forecast_executions.id", ondelete="CASCADE")
    )
    forecast_point_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("forecast_points.id", ondelete="CASCADE"), nullable=True
    )
    metric_code: Mapped[str] = mapped_column(String(40))
    metric_value: Mapped[float | None] = mapped_column(Numeric(38, 12), nullable=True)
    horizon_step: Mapped[int | None] = mapped_column(Integer, nullable=True)
    entity_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    evaluation_status: Mapped[str] = mapped_column(String(30))
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ForecastMethodRegistration(Base):
    __tablename__ = "forecast_method_registry"
    __table_args__ = (
        UniqueConstraint("method_code", "method_version", name="uq_forecast_method_version"),
        Index("ix_forecast_method_supported", "supported"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    method_code: Mapped[str] = mapped_column(String(100))
    method_name: Mapped[str] = mapped_column(String(200))
    method_version: Mapped[str] = mapped_column(String(30))
    capability_class: Mapped[str] = mapped_column(String(60))
    supported: Mapped[bool] = mapped_column(Boolean)
    minimum_history: Mapped[int] = mapped_column(Integer)
    minimum_seasonal_cycles: Mapped[int] = mapped_column(Integer)
    supports_trend: Mapped[bool] = mapped_column(Boolean)
    supports_seasonality: Mapped[bool] = mapped_column(Boolean)
    supports_exogenous: Mapped[bool] = mapped_column(Boolean)
    supports_intervals: Mapped[bool] = mapped_column(Boolean)
    supports_negative_values: Mapped[bool] = mapped_column(Boolean)
    supports_zero_values: Mapped[bool] = mapped_column(Boolean)
    supports_intermittent_demand: Mapped[bool] = mapped_column(Boolean)
    parameter_schema: Mapped[dict[str, object]] = mapped_column(portable_json)
    output_schema: Mapped[dict[str, object]] = mapped_column(portable_json)
    implementation_reference: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class ForecastExecutionStep(Base):
    __tablename__ = "forecast_execution_steps"
    __table_args__ = (
        UniqueConstraint(
            "forecast_execution_id", "sequence_number", name="uq_forecast_step_sequence"
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    forecast_execution_id: Mapped[UUID] = mapped_column(
        ForeignKey("forecast_executions.id", ondelete="CASCADE")
    )
    sequence_number: Mapped[int] = mapped_column(Integer)
    step_code: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    input_summary: Mapped[dict[str, object]] = mapped_column(portable_json)
    output_summary: Mapped[dict[str, object]] = mapped_column(portable_json)
    warning_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    explanation: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
