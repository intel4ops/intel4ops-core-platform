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


class StatisticalExecutionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    BLOCKED = "blocked"
    INSUFFICIENT_DATA = "insufficient_data"
    NOT_READY = "not_ready"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AnomalyDirection(StrEnum):
    ABOVE_EXPECTED = "above_expected"
    BELOW_EXPECTED = "below_expected"
    BIDIRECTIONAL = "bidirectional"
    LEVEL_SHIFT = "level_shift"
    TREND_INCREASE = "trend_increase"
    TREND_DECREASE = "trend_decrease"
    VOLATILITY_INCREASE = "volatility_increase"
    VOLATILITY_DECREASE = "volatility_decrease"


class AnomalySeverity(StrEnum):
    INFORMATIONAL = "informational"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class StatisticalExecution(Base):
    __tablename__ = "statistical_executions"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "idempotency_key", name="uq_statistical_execution_idempotency"
        ),
        CheckConstraint(
            f"status IN ({enum_values(StatisticalExecutionStatus)})",
            name="ck_statistical_execution_status",
        ),
        Index("ix_statistical_execution_org_status", "organization_id", "status"),
        Index("ix_statistical_execution_definition", "oikb_definition_version_id"),
        Index("ix_statistical_execution_fingerprint", "reproducibility_fingerprint"),
        Index("ix_statistical_execution_created", "created_at"),
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
    execution_package_fingerprint: Mapped[str] = mapped_column(String(64))
    reproducibility_fingerprint: Mapped[str] = mapped_column(String(64))
    method_code: Mapped[str] = mapped_column(String(100))
    method_version: Mapped[str] = mapped_column(String(30))
    analytical_level: Mapped[str] = mapped_column(String(30), default="statistical")
    status: Mapped[str] = mapped_column(String(30))
    requested_by: Mapped[UUID] = mapped_column(Uuid)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    blocked_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    trust_assessment_id: Mapped[UUID] = mapped_column(
        ForeignKey("trust_assessments.id", ondelete="RESTRICT")
    )
    readiness_assessment_id: Mapped[UUID] = mapped_column(
        ForeignKey("analytical_readiness_decisions.id", ondelete="RESTRICT")
    )
    dataset_reference: Mapped[str] = mapped_column(String(255))
    dataset_fingerprint: Mapped[str] = mapped_column(String(64))
    source_lineage_reference: Mapped[str] = mapped_column(String(500))
    parameter_snapshot: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    engine_version: Mapped[str] = mapped_column(String(30))
    correlation_id: Mapped[str] = mapped_column(String(100))
    idempotency_key: Mapped[str] = mapped_column(String(255))
    warnings: Mapped[list[str]] = mapped_column(portable_json, default=list)
    limitations: Mapped[list[str]] = mapped_column(portable_json, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    baselines: Mapped[list[StatisticalBaseline]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )
    observations: Mapped[list[StatisticalObservation]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )
    steps: Mapped[list[StatisticalExecutionStep]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )


class StatisticalBaseline(Base):
    __tablename__ = "statistical_baselines"
    __table_args__ = (
        Index(
            "ix_statistical_baseline_org_execution", "organization_id", "statistical_execution_id"
        ),
        Index("ix_statistical_baseline_fingerprint", "baseline_fingerprint"),
        CheckConstraint("record_count >= 0 AND entity_count >= 0", name="ck_baseline_counts"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    statistical_execution_id: Mapped[UUID] = mapped_column(
        ForeignKey("statistical_executions.id", ondelete="CASCADE")
    )
    baseline_type: Mapped[str] = mapped_column(String(40))
    baseline_scope: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    population_definition: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    time_window_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    time_window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    record_count: Mapped[int] = mapped_column(Integer)
    entity_count: Mapped[int] = mapped_column(Integer)
    mean_value: Mapped[float | None] = mapped_column(Numeric(38, 12), nullable=True)
    median_value: Mapped[float | None] = mapped_column(Numeric(38, 12), nullable=True)
    minimum_value: Mapped[float | None] = mapped_column(Numeric(38, 12), nullable=True)
    maximum_value: Mapped[float | None] = mapped_column(Numeric(38, 12), nullable=True)
    variance_value: Mapped[float | None] = mapped_column(Numeric(38, 12), nullable=True)
    standard_deviation_value: Mapped[float | None] = mapped_column(Numeric(38, 12), nullable=True)
    mad_value: Mapped[float | None] = mapped_column(Numeric(38, 12), nullable=True)
    percentile_values: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    baseline_fingerprint: Mapped[str] = mapped_column(String(64))
    limitations: Mapped[list[str]] = mapped_column(portable_json, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class StatisticalObservation(Base):
    __tablename__ = "statistical_observations"
    __table_args__ = (
        CheckConstraint(
            "statistical_score >= 0 AND statistical_score <= 1 AND "
            "confidence_score >= 0 AND confidence_score <= 1 AND "
            "materiality_score >= 0 AND materiality_score <= 1",
            name="ck_statistical_observation_scores",
        ),
        CheckConstraint(
            f"anomaly_direction IN ({enum_values(AnomalyDirection)})",
            name="ck_statistical_observation_direction",
        ),
        CheckConstraint(
            f"severity IN ({enum_values(AnomalySeverity)})",
            name="ck_statistical_observation_severity",
        ),
        Index(
            "ix_statistical_observation_org_execution",
            "organization_id",
            "statistical_execution_id",
        ),
        Index("ix_statistical_observation_anomaly", "organization_id", "is_anomaly"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    statistical_execution_id: Mapped[UUID] = mapped_column(
        ForeignKey("statistical_executions.id", ondelete="CASCADE")
    )
    entity_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    period_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    observed_value: Mapped[float] = mapped_column(Numeric(38, 12))
    expected_value: Mapped[float | None] = mapped_column(Numeric(38, 12), nullable=True)
    absolute_deviation: Mapped[float | None] = mapped_column(Numeric(38, 12), nullable=True)
    relative_deviation: Mapped[float | None] = mapped_column(Numeric(38, 12), nullable=True)
    normalized_deviation: Mapped[float | None] = mapped_column(Numeric(38, 12), nullable=True)
    statistical_score: Mapped[float] = mapped_column(Numeric(6, 5))
    confidence_score: Mapped[float] = mapped_column(Numeric(6, 5))
    materiality_score: Mapped[float] = mapped_column(Numeric(6, 5))
    anomaly_direction: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(20))
    is_anomaly: Mapped[bool] = mapped_column(Boolean)
    persistence_count: Mapped[int] = mapped_column(Integer, default=1)
    recurrence_count: Mapped[int] = mapped_column(Integer, default=1)
    method_trace: Mapped[dict[str, object]] = mapped_column(portable_json)
    explanation: Mapped[dict[str, object]] = mapped_column(portable_json)
    limitations: Mapped[list[str]] = mapped_column(portable_json, default=list)
    evidence_references: Mapped[list[dict[str, object]]] = mapped_column(
        portable_json, default=list
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    score_components: Mapped[list[StatisticalScoreComponent]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )


class StatisticalScoreComponent(Base):
    __tablename__ = "statistical_score_components"
    __table_args__ = (
        UniqueConstraint(
            "statistical_observation_id",
            "component_code",
            name="uq_statistical_score_component",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    statistical_observation_id: Mapped[UUID] = mapped_column(
        ForeignKey("statistical_observations.id", ondelete="CASCADE"), index=True
    )
    component_code: Mapped[str] = mapped_column(String(100))
    raw_value: Mapped[float] = mapped_column(Numeric(38, 12))
    normalized_value: Mapped[float] = mapped_column(Numeric(6, 5))
    weight: Mapped[float] = mapped_column(Numeric(6, 5))
    contribution: Mapped[float] = mapped_column(Numeric(6, 5))
    explanation: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class StatisticalExecutionStep(Base):
    __tablename__ = "statistical_execution_steps"
    __table_args__ = (
        UniqueConstraint(
            "statistical_execution_id", "sequence_number", name="uq_statistical_step_sequence"
        ),
        CheckConstraint("sequence_number > 0", name="ck_statistical_step_sequence"),
        Index("ix_statistical_step_execution", "statistical_execution_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    statistical_execution_id: Mapped[UUID] = mapped_column(
        ForeignKey("statistical_executions.id", ondelete="CASCADE")
    )
    sequence_number: Mapped[int] = mapped_column(Integer)
    step_code: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    input_summary: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    output_summary: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    warning_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    explanation: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class StatisticalMethodRegistration(Base):
    __tablename__ = "statistical_method_registry"
    __table_args__ = (
        UniqueConstraint("method_code", "method_version", name="uq_statistical_method_version"),
        Index("ix_statistical_method_capability", "capability_class"),
        Index("ix_statistical_method_supported", "supported"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    method_code: Mapped[str] = mapped_column(String(100))
    method_name: Mapped[str] = mapped_column(String(200))
    method_version: Mapped[str] = mapped_column(String(30))
    capability_class: Mapped[str] = mapped_column(String(60))
    supported: Mapped[bool] = mapped_column(Boolean)
    minimum_sample_size: Mapped[int] = mapped_column(Integer)
    supports_time_series: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_peer_group: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_grouping: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_weights: Mapped[bool] = mapped_column(Boolean, default=False)
    parameter_schema: Mapped[dict[str, object]] = mapped_column(portable_json)
    output_schema: Mapped[dict[str, object]] = mapped_column(portable_json)
    implementation_reference: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class AnomalySuppressionRecord(Base):
    __tablename__ = "anomaly_suppression_records"
    __table_args__ = (
        Index("ix_anomaly_suppression_org_definition", "organization_id", "definition_version_id"),
        Index("ix_anomaly_suppression_effective", "effective_from", "effective_to"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    definition_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("oikb_definition_versions.id", ondelete="RESTRICT")
    )
    entity_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    suppression_reason: Mapped[str] = mapped_column(Text)
    suppression_scope: Mapped[dict[str, object]] = mapped_column(portable_json)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AnomalyReviewFeedback(Base):
    __tablename__ = "anomaly_review_feedback"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "statistical_observation_id",
            "reviewer_id",
            name="uq_anomaly_review_reviewer",
        ),
        Index("ix_anomaly_review_org_observation", "organization_id", "statistical_observation_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    statistical_observation_id: Mapped[UUID] = mapped_column(
        ForeignKey("statistical_observations.id", ondelete="CASCADE")
    )
    review_status: Mapped[str] = mapped_column(String(30))
    reviewer_id: Mapped[UUID] = mapped_column(Uuid)
    classification: Mapped[str] = mapped_column(String(50))
    was_actionable: Mapped[bool] = mapped_column(Boolean)
    was_false_positive: Mapped[bool] = mapped_column(Boolean)
    confirmed_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str] = mapped_column(Text)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
