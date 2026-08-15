from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DecisionMethodRead(BaseModel):
    id: UUID
    method_code: str
    method_name: str
    method_class: str
    method_version: str
    solver_adapter: str
    solver_adapter_version: str
    exact_or_heuristic: str
    deterministic: bool
    certified_use_cases: tuple[str, ...]


class DecisionProblemCreate(BaseModel):
    problem_code: str = Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=150)
    problem_name: str = Field(min_length=1, max_length=250)
    use_case_code: Literal[
        "recovery_portfolio_selection",
        "technician_resource_assignment",
        "work_maintenance_sequencing",
    ]
    description: str = Field(min_length=1)
    scope_type: Literal["shared_core", "industry", "regional", "organization"]
    scope_key: str = Field(min_length=1, max_length=180)


class DecisionProblemRead(DecisionProblemCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_organization_id: UUID | None
    lifecycle_status: str
    created_by_user_id: UUID
    created_at: datetime


class DecisionProblemVersionCreate(BaseModel):
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$", max_length=30)
    objective_strategy: Literal["single", "weighted", "lexicographic"]
    input_contract: dict[str, object] = Field(default_factory=dict)
    output_contract: dict[str, object] = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class DecisionProblemVersionRead(DecisionProblemVersionCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    problem_id: UUID
    lifecycle_status: str
    content_hash: str
    published_at: datetime | None
    created_at: datetime


class DecisionObjectiveCreate(BaseModel):
    objective_code: str = Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=120)
    objective_type: str = Field(min_length=1, max_length=50)
    direction: Literal["maximize", "minimize"]
    source_metric: str = Field(min_length=1, max_length=150)
    weight: Decimal = Field(default=Decimal("1"), ge=0)
    priority_order: int = Field(default=1, ge=1)
    unit_code: str | None = None
    currency_code: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    parameters: dict[str, object] = Field(default_factory=dict)


class DecisionConstraintCreate(BaseModel):
    constraint_code: str = Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=120)
    constraint_type: str = Field(min_length=1, max_length=80)
    operator: Literal["<=", ">=", "=", "in"]
    right_hand_value: Decimal | None = None
    hard_constraint: bool = True
    unit_code: str | None = None
    currency_code: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    expression: dict[str, object] = Field(default_factory=dict)


class DecisionVariableCreate(BaseModel):
    variable_code: str = Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=120)
    variable_type: Literal["binary", "integer", "continuous", "assignment", "sequence"]
    lower_bound: Decimal | None = None
    upper_bound: Decimal | None = None
    unit_code: str | None = None
    domain_contract: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def bounds_are_ordered(self) -> "DecisionVariableCreate":
        if (
            self.lower_bound is not None
            and self.upper_bound is not None
            and self.lower_bound > self.upper_bound
        ):
            raise ValueError("lower_bound cannot exceed upper_bound")
        return self


class DecisionScenarioCreate(BaseModel):
    problem_version_id: UUID
    method_definition_id: UUID
    scenario_name: str = Field(min_length=1, max_length=250)
    scenario_horizon_start: datetime
    scenario_horizon_end: datetime
    timezone: str = Field(min_length=1, max_length=80)
    currency_code: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    idempotency_key: str = Field(min_length=8, max_length=255)

    @model_validator(mode="after")
    def horizon_is_ordered(self) -> "DecisionScenarioCreate":
        if self.scenario_horizon_end <= self.scenario_horizon_start:
            raise ValueError("scenario horizon end must follow start")
        return self


class DecisionScenarioInputCreate(BaseModel):
    input_kind: str = Field(min_length=1, max_length=80)
    source_id: UUID
    source_version: str | None = None
    source_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    mapping_confidence: Decimal | None = Field(default=None, ge=0, le=1)
    trust_readiness_status: str | None = None
    observed_at: datetime | None = None
    input_payload: dict[str, object] = Field(default_factory=dict)
    validation_flags: list[str] = Field(default_factory=list)


class DecisionScenarioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    problem_version_id: UUID
    method_definition_id: UUID
    scenario_name: str
    lifecycle_status: str
    scenario_horizon_start: datetime
    scenario_horizon_end: datetime
    timezone: str
    currency_code: str | None
    scenario_fingerprint: str
    validation_status: str
    gate_reasons: list[dict[str, object]]
    created_at: datetime


class DecisionExecutionCreate(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=255)
    time_limit_seconds: int = Field(default=30, ge=1, le=300)
    random_seed: int | None = None


class DecisionExecutionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    scenario_id: UUID
    method_code: str
    method_version: str
    solver_adapter: str
    solver_adapter_version: str
    status: str
    input_fingerprint: str
    scenario_fingerprint: str
    optimality_gap: Decimal | None
    duration_ms: int | None
    objective_values: dict[str, object]
    violations: list[dict[str, object]]
    warnings: list[str]
    assumptions: list[str]
    reproducibility_metadata: dict[str, object]
    gate_reasons: list[dict[str, object]]
    created_at: datetime


class DecisionAlternativeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    solution_id: UUID
    rank: int
    title: str
    selected: bool
    feasible: bool
    objective_values: dict[str, object]
    expected_value: Decimal | None
    expected_recovery: Decimal | None
    expected_cost: Decimal | None
    expected_risk: Decimal | None
    expected_duration_hours: Decimal | None
    currency_code: str | None
    binding_constraints: list[str]
    soft_constraint_violations: list[dict[str, object]]
    rejection_reason: str | None
    tradeoff_narrative: str
    assumptions: list[str]
    supporting_evidence: list[dict[str, object]]


class DecisionSolutionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    execution_id: UUID
    solution_number: int
    feasibility_status: str
    solver_status: str
    objective_values: dict[str, object]
    variable_values: dict[str, object]
    binding_constraints: list[str]
    violations: list[dict[str, object]]
    solver_metadata: dict[str, object]
    content_hash: str


class DecisionRecommendationCreate(BaseModel):
    solution_id: UUID
    selected_alternative_id: UUID
    title: str = Field(min_length=1, max_length=250)
    rationale: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=8, max_length=255)
    expires_at: datetime | None = None


class DecisionRecommendationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    solution_id: UUID
    selected_alternative_id: UUID
    approved_by_approval_id: UUID | None
    converted_action_id: UUID | None
    lifecycle_status: str
    title: str
    rationale: str
    objective_explanation: dict[str, object]
    constraint_explanation: dict[str, object]
    evidence_summary: list[dict[str, object]]
    expires_at: datetime | None
    created_at: datetime


class DecisionApprovalCreate(BaseModel):
    decision: Literal["approve", "reject", "defer", "request_changes"]
    rationale: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=8, max_length=255)


class DecisionApprovalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    recommendation_id: UUID
    decision: str
    rationale: str
    reviewer_user_id: UUID
    reviewer_role: str
    decided_at: datetime


class DecisionOutcomeCreate(BaseModel):
    operational_action_id: UUID
    action_outcome_id: UUID | None = None
    outcome_evidence_kind: Literal[
        "recovery_case",
        "recovery_execution",
        "verified_value_ledger_entry",
        "causal_outcome_assessment",
    ]
    outcome_evidence_id: UUID
    evidence_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    observed_at: datetime | None = None


class DecisionOutcomeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    recommendation_id: UUID
    operational_action_id: UUID
    action_outcome_id: UUID | None
    outcome_evidence_kind: str | None
    outcome_evidence_id: UUID | None
    evidence_fingerprint: str | None
    verification_status: str
    reconciliation_status: str
    expected_value_reference: str | None
    actual_value_reference: str | None
    observed_at: datetime | None


class DecisionSensitivityCreate(BaseModel):
    parameter_code: str = Field(min_length=1, max_length=120)
    perturbation_type: Literal[
        "objective_weight",
        "capacity",
        "budget",
        "cost",
        "recovery_probability",
        "time_horizon",
        "constraint_toggle",
    ]
    original_value: Decimal | None = None
    perturbed_value: Decimal | None = None


class DecisionHistoryEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_type: str
    entity_type: str
    entity_id: UUID
    summary: str
    occurred_at: datetime


class DecisionWorkspaceRecommendationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    solution_id: UUID
    selected_alternative_id: UUID
    approved_by_approval_id: UUID | None
    converted_action_id: UUID | None
    lifecycle_status: str
    title: str
    rationale: str
    objective_explanation: dict[str, object]
    constraint_explanation: dict[str, object]
    evidence_summary: list[dict[str, object]]
    expires_at: datetime | None
    created_by_user_id: UUID
    created_at: datetime
    updated_at: datetime


class DecisionWorkspaceHistoryEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_type: str
    entity_type: str
    entity_id: UUID
    actor_user_id: UUID | None
    actor_role: str | None
    summary: str
    event_metadata: dict[str, object]
    occurred_at: datetime


class DecisionWorkspaceRead(BaseModel):
    finding_id: UUID
    recommendation: DecisionWorkspaceRecommendationRead | None
    approval: DecisionApprovalRead | None
    history: list[DecisionWorkspaceHistoryEntry]
