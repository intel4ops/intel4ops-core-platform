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


class ReliabilityExecutionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    BLOCKED = "blocked"
    NOT_READY = "not_ready"
    INSUFFICIENT_DATA = "insufficient_data"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ReliabilityExecution(Base):
    __tablename__ = "reliability_executions"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "reproducibility_fingerprint", name="uq_reliability_reproducibility"
        ),
        CheckConstraint(
            f"status IN ({enum_values(ReliabilityExecutionStatus)})",
            name="ck_reliability_execution_status",
        ),
        Index("ix_reliability_execution_org_status", "organization_id", "status"),
        Index("ix_reliability_execution_asset_scope", "organization_id", "asset_scope_reference"),
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
    asset_scope_reference: Mapped[str] = mapped_column(String(255))
    asset_scope_type: Mapped[str] = mapped_column(String(40))
    reliability_method_code: Mapped[str] = mapped_column(String(100))
    reliability_method_version: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(40))
    requested_by: Mapped[UUID] = mapped_column(Uuid)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dataset_reference: Mapped[str] = mapped_column(String(255))
    dataset_fingerprint: Mapped[str] = mapped_column(String(64))
    lifecycle_fingerprint: Mapped[str] = mapped_column(String(64))
    source_lineage_reference: Mapped[str] = mapped_column(String(500))
    observation_window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    observation_window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    exposure_basis: Mapped[str] = mapped_column(String(40))
    exposure_unit: Mapped[str] = mapped_column(String(50))
    failure_definition_code: Mapped[str] = mapped_column(String(100))
    failure_definition_version: Mapped[str] = mapped_column(String(30))
    censoring_policy: Mapped[str] = mapped_column(String(50))
    engine_version: Mapped[str] = mapped_column(String(30))
    correlation_id: Mapped[str] = mapped_column(String(100))
    explanation: Mapped[dict[str, object]] = mapped_column(portable_json)
    warnings: Mapped[list[str]] = mapped_column(portable_json, default=list)
    limitations: Mapped[list[str]] = mapped_column(portable_json, default=list)
    failure_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    metrics: Mapped[list[ReliabilityMetric]] = relationship(cascade="all, delete-orphan")
    models: Mapped[list[ReliabilityModelResult]] = relationship(cascade="all, delete-orphan")
    steps: Mapped[list[ReliabilityExecutionStep]] = relationship(cascade="all, delete-orphan")


class ReliabilityMetric(Base):
    __tablename__ = "reliability_metrics"
    __table_args__ = (
        Index("ix_reliability_metric_org_execution", "organization_id", "reliability_execution_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    reliability_execution_id: Mapped[UUID] = mapped_column(
        ForeignKey("reliability_executions.id", ondelete="CASCADE")
    )
    asset_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metric_code: Mapped[str] = mapped_column(String(100))
    metric_value: Mapped[float | None] = mapped_column(Numeric(38, 12), nullable=True)
    metric_unit: Mapped[str] = mapped_column(String(50))
    numerator_value: Mapped[float | None] = mapped_column(Numeric(38, 12), nullable=True)
    denominator_value: Mapped[float | None] = mapped_column(Numeric(38, 12), nullable=True)
    exposure_basis: Mapped[str] = mapped_column(String(40))
    confidence_score: Mapped[float] = mapped_column(Numeric(8, 5))
    materiality_score: Mapped[float | None] = mapped_column(Numeric(8, 5), nullable=True)
    valid: Mapped[bool] = mapped_column(Boolean)
    invalid_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    method_trace: Mapped[dict[str, object]] = mapped_column(portable_json)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ReliabilityModelResult(Base):
    __tablename__ = "reliability_model_results"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    reliability_execution_id: Mapped[UUID] = mapped_column(
        ForeignKey("reliability_executions.id", ondelete="CASCADE")
    )
    asset_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    method_code: Mapped[str] = mapped_column(String(100))
    method_version: Mapped[str] = mapped_column(String(30))
    parameter_values: Mapped[dict[str, object]] = mapped_column(portable_json)
    fit_diagnostics: Mapped[dict[str, object]] = mapped_column(portable_json)
    sample_size: Mapped[int] = mapped_column(Integer)
    failure_count: Mapped[int] = mapped_column(Integer)
    censored_count: Mapped[int] = mapped_column(Integer)
    validation_status: Mapped[str] = mapped_column(String(40))
    limitations: Mapped[list[str]] = mapped_column(portable_json)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ReliabilityExecutionStep(Base):
    __tablename__ = "reliability_execution_steps"
    __table_args__ = (
        UniqueConstraint(
            "reliability_execution_id", "sequence_number", name="uq_reliability_step_sequence"
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    reliability_execution_id: Mapped[UUID] = mapped_column(
        ForeignKey("reliability_executions.id", ondelete="CASCADE")
    )
    sequence_number: Mapped[int] = mapped_column(Integer)
    step_code: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30))
    input_summary: Mapped[dict[str, object]] = mapped_column(portable_json)
    output_summary: Mapped[dict[str, object]] = mapped_column(portable_json)
    explanation: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ReliabilityMethodRegistration(Base):
    __tablename__ = "reliability_method_registry"
    __table_args__ = (
        UniqueConstraint("method_code", "method_version", name="uq_reliability_method_version"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    method_code: Mapped[str] = mapped_column(String(100))
    method_name: Mapped[str] = mapped_column(String(200))
    method_version: Mapped[str] = mapped_column(String(30))
    capability_class: Mapped[str] = mapped_column(String(80))
    supported: Mapped[bool] = mapped_column(Boolean)
    minimum_failure_count: Mapped[int] = mapped_column(Integer)
    minimum_asset_count: Mapped[int] = mapped_column(Integer)
    minimum_exposure: Mapped[float] = mapped_column(Numeric(38, 12))
    supports_censoring: Mapped[bool] = mapped_column(Boolean)
    supports_grouped_assets: Mapped[bool] = mapped_column(Boolean)
    supports_condition_inputs: Mapped[bool] = mapped_column(Boolean)
    supports_uncertainty: Mapped[bool] = mapped_column(Boolean)
    parameter_schema: Mapped[dict[str, object]] = mapped_column(portable_json)
    input_schema: Mapped[dict[str, object]] = mapped_column(portable_json)
    output_schema: Mapped[dict[str, object]] = mapped_column(portable_json)
    implementation_reference: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ReliabilityReviewFeedback(Base):
    __tablename__ = "reliability_review_feedback"
    __table_args__ = (
        Index("ix_reliability_review_org_execution", "organization_id", "reliability_execution_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    reliability_execution_id: Mapped[UUID] = mapped_column(
        ForeignKey("reliability_executions.id", ondelete="CASCADE")
    )
    assessment_type: Mapped[str] = mapped_column(String(50))
    assessment_reference: Mapped[str] = mapped_column(String(255))
    review_status: Mapped[str] = mapped_column(String(40))
    reviewer_id: Mapped[UUID] = mapped_column(Uuid)
    was_actionable: Mapped[bool] = mapped_column(Boolean)
    was_false_positive: Mapped[bool] = mapped_column(Boolean)
    notes: Mapped[str] = mapped_column(Text)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
