from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.engines.action_engine import ActionStatus
from app.models.entities import portable_json, utc_now
from app.models.source_system import enum_values


class OperationalAction(Base):
    __tablename__ = "operational_actions"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "idempotency_fingerprint", name="uq_action_idempotency"
        ),
        UniqueConstraint("organization_id", "id", name="uq_operational_actions_org_id"),
        ForeignKeyConstraint(
            ["organization_id", "reliability_execution_id"],
            ["reliability_executions.organization_id", "reliability_executions.id"],
            name="fk_operational_actions_org_reliability_execution",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "forecast_execution_id"],
            ["forecast_executions.organization_id", "forecast_executions.id"],
            name="fk_operational_actions_org_forecast_execution",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "orchestration_request_id"],
            [
                "intelligence_orchestration_requests.organization_id",
                "intelligence_orchestration_requests.id",
            ],
            name="fk_operational_actions_org_orchestration_request",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            f"status IN ({enum_values(ActionStatus)})", name="ck_operational_action_status"
        ),
        Index("ix_action_org_status", "organization_id", "status"),
        Index("ix_action_org_source", "organization_id", "source_type", "source_reference"),
        Index("ix_action_org_due", "organization_id", "due_at"),
        Index(
            "ix_action_org_reliability_execution",
            "organization_id",
            "reliability_execution_id",
        ),
        Index(
            "ix_action_org_forecast_execution",
            "organization_id",
            "forecast_execution_id",
        ),
        Index(
            "ix_action_org_orchestration_request",
            "organization_id",
            "orchestration_request_id",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    source_type: Mapped[str] = mapped_column(String(40))
    source_reference: Mapped[str] = mapped_column(String(255))
    reliability_execution_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("reliability_executions.id", ondelete="RESTRICT"), nullable=True
    )
    finding_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("findings.id", ondelete="RESTRICT"), nullable=True
    )
    forecast_execution_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("forecast_executions.id", ondelete="RESTRICT"), nullable=True
    )
    orchestration_request_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("intelligence_orchestration_requests.id", ondelete="RESTRICT"), nullable=True
    )
    recommendation_type: Mapped[str] = mapped_column(String(80))
    recommendation_rule_version: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(250))
    description: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text)
    asset_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    component_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    failure_mode: Mapped[str | None] = mapped_column(String(150), nullable=True)
    priority: Mapped[str] = mapped_column(String(20))
    priority_score: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    priority_components: Mapped[dict[str, object]] = mapped_column(portable_json)
    status: Mapped[str] = mapped_column(String(40))
    approval_required: Mapped[bool] = mapped_column(Boolean)
    approval_level: Mapped[str] = mapped_column(String(50))
    approval_role: Mapped[str] = mapped_column(String(50))
    approval_status: Mapped[str] = mapped_column(String(40))
    assigned_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    assigned_role: Mapped[str | None] = mapped_column(String(50), nullable=True)
    assigned_team: Mapped[str | None] = mapped_column(String(150), nullable=True)
    verification_required: Mapped[bool] = mapped_column(Boolean, default=True)
    verification_owner_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scheduled_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scheduled_finish: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expected_avoided_cost: Mapped[Decimal | None] = mapped_column(Numeric(38, 12), nullable=True)
    expected_intervention_cost: Mapped[Decimal | None] = mapped_column(
        Numeric(38, 12), nullable=True
    )
    currency_code: Mapped[str | None] = mapped_column(String(3), nullable=True)
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 5), nullable=True)
    limitations: Mapped[list[str]] = mapped_column(portable_json, default=list)
    evidence_references: Mapped[list[dict[str, object]]] = mapped_column(
        portable_json, default=list
    )
    idempotency_fingerprint: Mapped[str] = mapped_column(String(64))
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ActionPlanStep(Base):
    __tablename__ = "action_plan_steps"
    __table_args__ = (
        UniqueConstraint("action_id", "sequence_number", name="uq_action_plan_step_sequence"),
        ForeignKeyConstraint(
            ["organization_id", "action_id"],
            ["operational_actions.organization_id", "operational_actions.id"],
            name="fk_action_plan_steps_org_action",
            ondelete="CASCADE",
        ),
        Index("ix_action_plan_step_org_action", "organization_id", "action_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    action_id: Mapped[UUID] = mapped_column(
        ForeignKey("operational_actions.id", ondelete="CASCADE")
    )
    sequence_number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(250))
    description: Mapped[str] = mapped_column(Text)
    required_skill: Mapped[str | None] = mapped_column(String(150), nullable=True)
    labor_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    estimated_labor_hours: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    required_tools: Mapped[list[str]] = mapped_column(portable_json, default=list)
    required_permits: Mapped[list[str]] = mapped_column(portable_json, default=list)
    work_order_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_system_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="planned")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ActionDependency(Base):
    __tablename__ = "action_dependencies"
    __table_args__ = (
        UniqueConstraint("action_id", "prerequisite_action_id", name="uq_action_dependency_pair"),
        CheckConstraint("action_id <> prerequisite_action_id", name="ck_action_dependency_self"),
        ForeignKeyConstraint(
            ["organization_id", "action_id"],
            ["operational_actions.organization_id", "operational_actions.id"],
            name="fk_action_dependencies_org_action",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "prerequisite_action_id"],
            ["operational_actions.organization_id", "operational_actions.id"],
            name="fk_action_dependencies_org_prerequisite",
            ondelete="RESTRICT",
        ),
        Index("ix_action_dependency_org_action", "organization_id", "action_id"),
        Index(
            "ix_action_dependency_org_prerequisite",
            "organization_id",
            "prerequisite_action_id",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    action_id: Mapped[UUID] = mapped_column(
        ForeignKey("operational_actions.id", ondelete="CASCADE")
    )
    prerequisite_action_id: Mapped[UUID] = mapped_column(
        ForeignKey("operational_actions.id", ondelete="RESTRICT")
    )
    dependency_type: Mapped[str] = mapped_column(String(50))
    mandatory: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(30), default="unresolved")
    blocking_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ActionResourceRequirement(Base):
    __tablename__ = "action_resource_requirements"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "action_id"],
            ["operational_actions.organization_id", "operational_actions.id"],
            name="fk_action_resource_requirements_org_action",
            ondelete="CASCADE",
        ),
        Index("ix_action_resource_org_action", "organization_id", "action_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    action_id: Mapped[UUID] = mapped_column(
        ForeignKey("operational_actions.id", ondelete="CASCADE")
    )
    resource_type: Mapped[str] = mapped_column(String(40))
    resource_identifier: Mapped[str] = mapped_column(String(150))
    description: Mapped[str] = mapped_column(Text)
    required_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    available_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    mandatory: Mapped[bool] = mapped_column(Boolean, default=True)
    inventory_check_status: Mapped[str] = mapped_column(String(40), default="unknown")
    reservation_status: Mapped[str] = mapped_column(String(40), default="not_requested")
    reservation_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_system_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    required_by: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    shortage: Mapped[bool] = mapped_column(Boolean, default=False)
    limitation: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ActionEvent(Base):
    __tablename__ = "action_events"
    __table_args__ = (
        UniqueConstraint("action_id", "idempotency_key", name="uq_action_event_idempotency"),
        ForeignKeyConstraint(
            ["organization_id", "action_id"],
            ["operational_actions.organization_id", "operational_actions.id"],
            name="fk_action_events_org_action",
            ondelete="CASCADE",
        ),
        Index("ix_action_event_org_action", "organization_id", "action_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    action_id: Mapped[UUID] = mapped_column(
        ForeignKey("operational_actions.id", ondelete="CASCADE")
    )
    event_type: Mapped[str] = mapped_column(String(50))
    prior_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    new_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    actor_user_id: Mapped[UUID] = mapped_column(Uuid)
    actor_role: Mapped[str] = mapped_column(String(50))
    reason_code: Mapped[str] = mapped_column(String(100))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    idempotency_key: Mapped[str] = mapped_column(String(255))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ActionEvidence(Base):
    __tablename__ = "action_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "action_id"],
            ["operational_actions.organization_id", "operational_actions.id"],
            name="fk_action_evidence_org_action",
            ondelete="CASCADE",
        ),
        Index("ix_action_evidence_org_action", "organization_id", "action_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    action_id: Mapped[UUID] = mapped_column(
        ForeignKey("operational_actions.id", ondelete="CASCADE")
    )
    lifecycle_stage: Mapped[str] = mapped_column(String(40))
    evidence_type: Mapped[str] = mapped_column(String(50))
    source_type: Mapped[str] = mapped_column(String(50))
    source_identifier: Mapped[str] = mapped_column(String(255))
    document_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    measurement_value: Mapped[Decimal | None] = mapped_column(Numeric(38, 12), nullable=True)
    measurement_unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actor_user_id: Mapped[UUID] = mapped_column(Uuid)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    integrity_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ActionOutcome(Base):
    __tablename__ = "action_outcomes"
    __table_args__ = (
        UniqueConstraint("action_id", "outcome_type", name="uq_action_outcome_type"),
        UniqueConstraint("organization_id", "id", name="uq_action_outcomes_org_id"),
        ForeignKeyConstraint(
            ["organization_id", "action_id"],
            ["operational_actions.organization_id", "operational_actions.id"],
            name="fk_action_outcomes_org_action",
            ondelete="CASCADE",
        ),
        Index("ix_action_outcome_org_action", "organization_id", "action_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    action_id: Mapped[UUID] = mapped_column(
        ForeignKey("operational_actions.id", ondelete="CASCADE")
    )
    outcome_type: Mapped[str] = mapped_column(String(30))
    avoided_cost: Mapped[Decimal | None] = mapped_column(Numeric(38, 12), nullable=True)
    intervention_cost: Mapped[Decimal | None] = mapped_column(Numeric(38, 12), nullable=True)
    downtime_avoided: Mapped[Decimal | None] = mapped_column(Numeric(38, 12), nullable=True)
    production_preserved: Mapped[Decimal | None] = mapped_column(Numeric(38, 12), nullable=True)
    risk_reduction: Mapped[Decimal | None] = mapped_column(Numeric(8, 5), nullable=True)
    currency_code: Mapped[str | None] = mapped_column(String(3), nullable=True)
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 5), nullable=True)
    calculation_method: Mapped[str] = mapped_column(String(100))
    verification_method: Mapped[str | None] = mapped_column(String(100), nullable=True)
    verified_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assumptions: Mapped[list[str]] = mapped_column(portable_json, default=list)
    limitations: Mapped[list[str]] = mapped_column(portable_json, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ActionModelFeedback(Base):
    __tablename__ = "action_model_feedback"
    __table_args__ = (
        UniqueConstraint("action_id", "reliability_execution_id", name="uq_action_feedback"),
        ForeignKeyConstraint(
            ["organization_id", "action_id"],
            ["operational_actions.organization_id", "operational_actions.id"],
            name="fk_action_model_feedback_org_action",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "reliability_execution_id"],
            ["reliability_executions.organization_id", "reliability_executions.id"],
            name="fk_action_model_feedback_org_reliability_execution",
            ondelete="RESTRICT",
        ),
        Index("ix_action_feedback_org_action", "organization_id", "action_id"),
        Index(
            "ix_action_feedback_org_reliability_execution",
            "organization_id",
            "reliability_execution_id",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    action_id: Mapped[UUID] = mapped_column(
        ForeignKey("operational_actions.id", ondelete="CASCADE")
    )
    reliability_execution_id: Mapped[UUID] = mapped_column(
        ForeignKey("reliability_executions.id", ondelete="RESTRICT")
    )
    prediction_outcome_classification: Mapped[str] = mapped_column(String(50))
    intervention_performed: Mapped[bool] = mapped_column(Boolean)
    failure_occurred: Mapped[bool] = mapped_column(Boolean)
    failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    risk_reduced: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    predicted_probability: Mapped[Decimal | None] = mapped_column(Numeric(8, 6), nullable=True)
    predicted_horizon_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_time_to_event_days: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    recommendation_accepted: Mapped[bool] = mapped_column(Boolean)
    recommendation_executed: Mapped[bool] = mapped_column(Boolean)
    calibration_feedback: Mapped[dict[str, object]] = mapped_column(portable_json)
    human_review_status: Mapped[str] = mapped_column(String(40))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
