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
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.entities import utc_now
from app.models.source_system import enum_values, portable_json


class OrchestrationStatus(StrEnum):
    RECEIVED = "received"
    VALIDATING = "validating"
    DECIDING = "deciding"
    EXECUTING = "executing"
    COMPLETED = "completed"
    COMPLETED_WITH_LIMITATIONS = "completed_with_limitations"
    PARTIALLY_COMPLETED = "partially_completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"
    CANCELLED = "cancelled"


class OrchestrationDecisionType(StrEnum):
    EXECUTE = "execute"
    EXECUTE_WITH_WARNINGS = "execute_with_warnings"
    RETURN_EXISTING_RESULT = "return_existing_result"
    BLOCK = "block"
    DEFER = "defer"
    UNSUPPORTED = "unsupported"
    ESCALATE = "escalate"
    STOP_WITH_CURRENT_RESULT = "stop_with_current_result"


class OrchestrationStepStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    SKIPPED = "skipped"


class EngineRegistrationStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    DEPRECATED = "deprecated"
    UNAVAILABLE = "unavailable"
    EXPERIMENTAL = "experimental"


class IntelligenceOrchestrationRequest(Base):
    __tablename__ = "intelligence_orchestration_requests"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_orchestration_requests_organization_idempotency",
        ),
        UniqueConstraint(
            "organization_id",
            "correlation_id",
            name="uq_orchestration_requests_organization_correlation",
        ),
        CheckConstraint(
            f"status IN ({enum_values(OrchestrationStatus)})",
            name="ck_orchestration_request_status",
        ),
        Index(
            "ix_orchestration_requests_organization_status",
            "organization_id",
            "status",
        ),
        Index(
            "ix_orchestration_requests_organization_definition",
            "organization_id",
            "definition_code",
            "definition_version",
        ),
        Index(
            "ix_orchestration_requests_organization_requested",
            "organization_id",
            "requested_at",
        ),
        Index("ix_orchestration_requests_dataset_id", "dataset_id"),
        Index("ix_orchestration_requests_trust_assessment_id", "trust_assessment_id"),
        Index("ix_orchestration_requests_readiness_id", "analytical_readiness_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    request_code: Mapped[str] = mapped_column(String(40), unique=True)
    correlation_id: Mapped[str] = mapped_column(String(100))
    idempotency_key: Mapped[str] = mapped_column(String(255))
    definition_code: Mapped[str] = mapped_column(String(100))
    definition_version: Mapped[str] = mapped_column(String(30))
    requested_analytical_level: Mapped[str | None] = mapped_column(String(40), nullable=True)
    dataset_id: Mapped[UUID] = mapped_column(ForeignKey("datasets.id", ondelete="RESTRICT"))
    dataset_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="RESTRICT"), nullable=True
    )
    dataset_reference: Mapped[str] = mapped_column(String(255))
    trust_assessment_id: Mapped[UUID] = mapped_column(
        ForeignKey("trust_assessments.id", ondelete="RESTRICT")
    )
    analytical_readiness_id: Mapped[UUID] = mapped_column(
        ForeignKey("analytical_readiness_decisions.id", ondelete="RESTRICT")
    )
    requested_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    status: Mapped[str] = mapped_column(String(40))
    publish_finding: Mapped[bool] = mapped_column(Boolean, default=False)
    parameters_summary: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    request_context: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    context_fingerprint: Mapped[str] = mapped_column(String(64))
    warnings: Mapped[list[str]] = mapped_column(portable_json, default=list)
    limitations: Mapped[list[str]] = mapped_column(portable_json, default=list)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    decisions: Mapped[list["IntelligenceOrchestrationDecision"]] = relationship(
        back_populates="request", cascade="all, delete-orphan", passive_deletes=True
    )
    steps: Mapped[list["IntelligenceOrchestrationStep"]] = relationship(
        back_populates="request", cascade="all, delete-orphan", passive_deletes=True
    )
    history: Mapped[list["IntelligenceOrchestrationStatusHistory"]] = relationship(
        back_populates="request", cascade="all, delete-orphan", passive_deletes=True
    )


class IntelligenceOrchestrationDecision(Base):
    __tablename__ = "intelligence_orchestration_decisions"
    __table_args__ = (
        UniqueConstraint(
            "orchestration_request_id",
            "decision_sequence",
            name="uq_orchestration_decision_sequence",
        ),
        CheckConstraint(
            f"decision IN ({enum_values(OrchestrationDecisionType)})",
            name="ck_orchestration_decision_type",
        ),
        Index(
            "ix_orchestration_decisions_organization_request",
            "organization_id",
            "orchestration_request_id",
        ),
        Index(
            "ix_orchestration_decisions_selected_engine",
            "selected_engine_code",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    orchestration_request_id: Mapped[UUID] = mapped_column(
        ForeignKey("intelligence_orchestration_requests.id", ondelete="CASCADE")
    )
    decision_sequence: Mapped[int] = mapped_column(Integer)
    definition_code: Mapped[str] = mapped_column(String(100))
    definition_version: Mapped[str] = mapped_column(String(30))
    requested_level: Mapped[str | None] = mapped_column(String(40), nullable=True)
    selected_level: Mapped[str | None] = mapped_column(String(40), nullable=True)
    selected_engine_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    selected_engine_version: Mapped[str | None] = mapped_column(String(30), nullable=True)
    alternatives_considered: Mapped[list[dict[str, object]]] = mapped_column(
        portable_json, default=list
    )
    trust_status: Mapped[str] = mapped_column(String(40))
    readiness_status: Mapped[str] = mapped_column(String(40))
    evaluated_readiness_level: Mapped[str | None] = mapped_column(String(40), nullable=True)
    readiness_mapping_policy_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    readiness_mapping_policy_version: Mapped[str | None] = mapped_column(String(30), nullable=True)
    warnings: Mapped[list[str]] = mapped_column(portable_json, default=list)
    sufficiency_status: Mapped[str] = mapped_column(String(40))
    escalation_status: Mapped[str] = mapped_column(String(40))
    decision: Mapped[str] = mapped_column(String(40))
    decision_reason_code: Mapped[str] = mapped_column(String(100))
    decision_summary: Mapped[str] = mapped_column(Text)
    policy_code: Mapped[str] = mapped_column(String(100))
    policy_version: Mapped[str] = mapped_column(String(30))
    content_hash: Mapped[str] = mapped_column(String(64))
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    request: Mapped[IntelligenceOrchestrationRequest] = relationship(back_populates="decisions")


class IntelligenceOrchestrationStep(Base):
    __tablename__ = "intelligence_orchestration_steps"
    __table_args__ = (
        UniqueConstraint(
            "orchestration_request_id",
            "step_sequence",
            name="uq_orchestration_step_sequence",
        ),
        CheckConstraint(
            f"status IN ({enum_values(OrchestrationStepStatus)})",
            name="ck_orchestration_step_status",
        ),
        CheckConstraint("step_sequence > 0", name="ck_orchestration_step_sequence"),
        Index(
            "ix_orchestration_steps_organization_request",
            "organization_id",
            "orchestration_request_id",
        ),
        Index(
            "ix_orchestration_steps_execution",
            "organization_id",
            "source_execution_id",
        ),
        Index("ix_orchestration_steps_finding_id", "finding_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    orchestration_request_id: Mapped[UUID] = mapped_column(
        ForeignKey("intelligence_orchestration_requests.id", ondelete="CASCADE")
    )
    step_sequence: Mapped[int] = mapped_column(Integer)
    analytical_level: Mapped[str | None] = mapped_column(String(40), nullable=True)
    engine_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    engine_version: Mapped[str | None] = mapped_column(String(30), nullable=True)
    step_type: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(30))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_execution_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("intelligence_executions.id", ondelete="RESTRICT"), nullable=True
    )
    source_result_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("intelligence_executions.id", ondelete="RESTRICT"), nullable=True
    )
    result_locator: Mapped[str | None] = mapped_column(String(100), nullable=True)
    output_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    finding_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("findings.id", ondelete="RESTRICT"), nullable=True
    )
    input_reference_summary: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    output_reference_summary: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    warnings: Mapped[list[str]] = mapped_column(portable_json, default=list)
    limitations: Mapped[list[str]] = mapped_column(portable_json, default=list)
    block_reason_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    request: Mapped[IntelligenceOrchestrationRequest] = relationship(back_populates="steps")


class IntelligenceEngineRegistration(Base):
    __tablename__ = "intelligence_engine_registrations"
    __table_args__ = (
        UniqueConstraint(
            "engine_code",
            "engine_version",
            name="uq_engine_registration_code_version",
        ),
        CheckConstraint(
            f"status IN ({enum_values(EngineRegistrationStatus)})",
            name="ck_engine_registration_status",
        ),
        Index("ix_engine_registrations_level", "analytical_level"),
        Index("ix_engine_registrations_capability", "capability_code"),
        Index("ix_engine_registrations_available", "is_available"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    engine_code: Mapped[str] = mapped_column(String(100))
    engine_name: Mapped[str] = mapped_column(String(200))
    engine_version: Mapped[str] = mapped_column(String(30))
    analytical_level: Mapped[str] = mapped_column(String(40))
    capability_code: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30))
    is_available: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_sync: Mapped[bool] = mapped_column(Boolean, default=True)
    supports_async: Mapped[bool] = mapped_column(Boolean, default=False)
    input_contract_version: Mapped[str] = mapped_column(String(30))
    output_contract_version: Mapped[str] = mapped_column(String(30))
    implementation_reference: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class IntelligenceOrchestrationStatusHistory(Base):
    __tablename__ = "intelligence_orchestration_status_history"
    __table_args__ = (
        UniqueConstraint(
            "orchestration_request_id",
            "transition_sequence",
            name="uq_orchestration_history_sequence",
        ),
        CheckConstraint("transition_sequence > 0", name="ck_orchestration_history_sequence"),
        Index(
            "ix_orchestration_history_organization_request",
            "organization_id",
            "orchestration_request_id",
        ),
        Index("ix_orchestration_history_changed_at", "changed_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    orchestration_request_id: Mapped[UUID] = mapped_column(
        ForeignKey("intelligence_orchestration_requests.id", ondelete="CASCADE")
    )
    transition_sequence: Mapped[int] = mapped_column(Integer)
    previous_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    new_status: Mapped[str] = mapped_column(String(40))
    reason_code: Mapped[str] = mapped_column(String(100))
    changed_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    metadata_json: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)

    request: Mapped[IntelligenceOrchestrationRequest] = relationship(back_populates="history")
