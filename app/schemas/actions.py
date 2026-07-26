from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.engines.action_engine import ActionStatus


class ActionCreate(BaseModel):
    source_type: str = Field(pattern=r"^(manual|reliability|finding|forecasting|trust|recovery)$")
    source_reference: str = Field(min_length=1, max_length=255)
    reliability_execution_id: UUID | None = None
    finding_id: UUID | None = None
    forecast_execution_id: UUID | None = None
    orchestration_request_id: UUID | None = None
    recommendation_type: str = Field(min_length=1, max_length=80)
    recommendation_rule_version: str = Field(default="1.0", max_length=30)
    title: str = Field(min_length=1, max_length=250)
    description: str = Field(min_length=1, max_length=4000)
    rationale: str = Field(min_length=1, max_length=4000)
    asset_reference: str | None = Field(default=None, max_length=255)
    component_reference: str | None = Field(default=None, max_length=255)
    failure_mode: str | None = Field(default=None, max_length=150)
    failure_probability: Decimal | None = Field(default=None, ge=0, le=1)
    prediction_horizon_days: int | None = Field(default=None, ge=1, le=3650)
    severity: int = Field(default=3, ge=1, le=5)
    confidence_score: Decimal | None = Field(default=None, ge=0, le=1)
    expected_avoided_cost: Decimal | None = Field(default=None, ge=0)
    expected_intervention_cost: Decimal | None = Field(default=None, ge=0)
    currency_code: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    due_at: datetime | None = None
    sensitive: bool = False
    verification_required: bool = True
    evidence_references: list[dict[str, object]] = Field(default_factory=list, max_length=100)
    limitations: list[str] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def source_contract(self) -> "ActionCreate":
        expected = {
            "reliability": self.reliability_execution_id,
            "finding": self.finding_id,
            "forecasting": self.forecast_execution_id,
        }.get(self.source_type)
        if self.source_type in {"reliability", "finding", "forecasting"} and expected is None:
            raise ValueError("The typed source identifier is required")
        if (
            self.expected_avoided_cost is not None or self.expected_intervention_cost is not None
        ) and self.currency_code is None:
            raise ValueError("Currency is required for monetary values")
        return self


class ActionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    source_type: str
    source_reference: str
    reliability_execution_id: UUID | None
    finding_id: UUID | None
    forecast_execution_id: UUID | None
    title: str
    description: str
    rationale: str
    asset_reference: str | None
    failure_mode: str | None
    priority: str
    priority_score: Decimal
    status: ActionStatus
    approval_required: bool
    approval_status: str
    assigned_user_id: UUID | None
    assigned_role: str | None
    verification_required: bool
    due_at: datetime | None
    completed_at: datetime | None
    verified_at: datetime | None
    expected_avoided_cost: Decimal | None
    expected_intervention_cost: Decimal | None
    currency_code: str | None
    limitations: list[str]
    created_at: datetime


class ActionPage(BaseModel):
    items: list[ActionRead]
    page: int
    page_size: int
    total: int


class ActionTransitionCreate(BaseModel):
    new_status: ActionStatus
    reason_code: str = Field(min_length=1, max_length=100)
    note: str | None = Field(default=None, max_length=4000)
    idempotency_key: str = Field(min_length=1, max_length=255)


class ActionAssignmentCreate(BaseModel):
    assigned_user_id: UUID | None = None
    assigned_role: str | None = Field(default=None, max_length=50)
    assigned_team: str | None = Field(default=None, max_length=150)
    due_at: datetime | None = None
    idempotency_key: str = Field(min_length=1, max_length=255)


class ActionPlanStepCreate(BaseModel):
    sequence_number: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=250)
    description: str = Field(min_length=1, max_length=4000)
    required_skill: str | None = Field(default=None, max_length=150)
    labor_category: str | None = Field(default=None, max_length=100)
    estimated_labor_hours: Decimal | None = Field(default=None, ge=0)
    required_tools: list[str] = Field(default_factory=list)
    required_permits: list[str] = Field(default_factory=list)
    work_order_reference: str | None = Field(default=None, max_length=255)
    external_system_reference: str | None = Field(default=None, max_length=255)


class ActionDependencyCreate(BaseModel):
    prerequisite_action_id: UUID
    dependency_type: str = Field(min_length=1, max_length=50)
    mandatory: bool = True
    blocking_reason: str | None = Field(default=None, max_length=4000)


class ActionResourceCreate(BaseModel):
    resource_type: str = Field(pattern=r"^(part|skill|labor|tool|permit|document)$")
    resource_identifier: str = Field(min_length=1, max_length=150)
    description: str = Field(min_length=1, max_length=4000)
    required_quantity: Decimal = Field(gt=0)
    available_quantity: Decimal | None = Field(default=None, ge=0)
    mandatory: bool = True
    source_system_reference: str | None = Field(default=None, max_length=255)
    required_by: datetime | None = None
    limitation: str | None = Field(default=None, max_length=4000)


class ActionEvidenceCreate(BaseModel):
    lifecycle_stage: str = Field(min_length=1, max_length=40)
    evidence_type: str = Field(min_length=1, max_length=50)
    source_type: str = Field(min_length=1, max_length=50)
    source_identifier: str = Field(min_length=1, max_length=255)
    document_reference: str | None = Field(default=None, max_length=500)
    measurement_value: Decimal | None = None
    measurement_unit: str | None = Field(default=None, max_length=50)
    observed_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=4000)
    metadata_json: dict[str, object] = Field(default_factory=dict)
    integrity_fingerprint: str | None = Field(default=None, max_length=128)


class ActionOutcomeCreate(BaseModel):
    outcome_type: str = Field(pattern=r"^(expected|realized)$")
    avoided_cost: Decimal | None = Field(default=None, ge=0)
    intervention_cost: Decimal | None = Field(default=None, ge=0)
    downtime_avoided: Decimal | None = Field(default=None, ge=0)
    production_preserved: Decimal | None = Field(default=None, ge=0)
    risk_reduction: Decimal | None = Field(default=None, ge=0, le=1)
    currency_code: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    confidence_score: Decimal | None = Field(default=None, ge=0, le=1)
    calculation_method: str = Field(min_length=1, max_length=100)
    verification_method: str | None = Field(default=None, max_length=100)
    assumptions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ActionFeedbackCreate(BaseModel):
    failure_occurred: bool
    failure_at: datetime | None = None
    intervention_performed: bool
    risk_reduced: bool | None = None
    predicted_positive: bool = True
    observation_window_complete: bool
    predicted_probability: Decimal | None = Field(default=None, ge=0, le=1)
    predicted_horizon_days: int | None = Field(default=None, ge=1)
    actual_time_to_event_days: Decimal | None = Field(default=None, ge=0)
    recommendation_accepted: bool
    recommendation_executed: bool
    calibration_feedback: dict[str, object] = Field(default_factory=dict)
    human_review_status: str = Field(default="pending", max_length=40)
    notes: str | None = Field(default=None, max_length=4000)
