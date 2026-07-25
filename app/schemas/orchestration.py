from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.findings import CandidateFindingCreate
from app.schemas.intelligence import EvidenceReference, ExecutionType


class OrchestrationAnalyticalLevel(StrEnum):
    ARITHMETIC = "arithmetic"
    RULE_BASED = "rule_based"
    STATISTICAL = "statistical"
    FORECASTING = "forecasting"
    PREDICTIVE = "predictive"
    RELIABILITY = "reliability"
    OPTIMIZATION = "optimization"
    SIMULATION = "simulation"
    RECOVERY = "recovery"


class OrchestrationStatusValue(StrEnum):
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


class SufficiencyStatus(StrEnum):
    SUFFICIENT = "sufficient"
    SUFFICIENT_WITH_LIMITATIONS = "sufficient_with_limitations"
    INSUFFICIENT = "insufficient"
    NOT_EVALUATED = "not_evaluated"


class EscalationStatus(StrEnum):
    NOT_REQUIRED = "not_required"
    ELIGIBLE = "eligible"
    NOT_READY = "not_ready"
    NOT_SUPPORTED = "not_supported"
    NOT_AUTHORIZED = "not_authorized"
    BLOCKED_BY_TRUST = "blocked_by_trust"
    BLOCKED_BY_POLICY = "blocked_by_policy"
    DEFERRED = "deferred"


class OrchestrationStepType(StrEnum):
    VALIDATION = "validation"
    TRUST_CHECK = "trust_check"
    READINESS_CHECK = "readiness_check"
    DEFINITION_RESOLUTION = "definition_resolution"
    ENGINE_SELECTION = "engine_selection"
    EXECUTION = "execution"
    SUFFICIENCY_EVALUATION = "sufficiency_evaluation"
    ESCALATION_EVALUATION = "escalation_evaluation"
    FINDING_PUBLICATION = "finding_publication"
    COMPLETION = "completion"


class AnalyticalOutputReference(BaseModel):
    execution_id: UUID
    result_id: UUID
    result_locator: str = Field(min_length=1, max_length=100)
    output_index: int = Field(ge=0)


class OrchestrationCreate(BaseModel):
    definition_code: str = Field(
        pattern=r"^(?:[a-z][a-z0-9_]*|[A-Z][A-Z0-9_]*(?:\.[A-Z][A-Z0-9_]*)+)$",
        max_length=100,
    )
    definition_version: str = Field(pattern=r"^[0-9]+(?:\.[0-9]+)*$", max_length=30)
    dataset_id: UUID
    dataset_version_id: UUID | None = None
    dataset_reference: str = Field(min_length=1, max_length=255)
    trust_assessment_id: UUID
    analytical_readiness_id: UUID
    requested_analytical_level: OrchestrationAnalyticalLevel | None = None
    records: list[dict[str, object]] = Field(default_factory=list, max_length=1000)
    parameters: dict[str, object] = Field(default_factory=dict, max_length=30)
    execution_type: ExecutionType
    unit: str | None = Field(default=None, max_length=50)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    evidence: list[EvidenceReference] = Field(default_factory=list, max_length=200)
    publish_finding: bool = False
    finding_candidate: CandidateFindingCreate | None = None
    allow_arithmetic_fallback: bool = True
    correlation_id: str = Field(min_length=1, max_length=100)
    idempotency_key: str = Field(min_length=1, max_length=255)
    request_context: dict[str, object] = Field(default_factory=dict, max_length=20)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.upper()
        if not value.isascii() or not value.isalpha():
            raise ValueError("Currency must contain three ASCII letters")
        return value

    @model_validator(mode="after")
    def validate_publication(self) -> "OrchestrationCreate":
        if self.publish_finding != (self.finding_candidate is not None):
            raise ValueError("publish_finding and finding_candidate must be supplied together")
        return self


class OrchestrationDecisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    decision_sequence: int
    definition_code: str
    definition_version: str
    requested_level: str | None
    selected_level: str | None
    selected_engine_code: str | None
    selected_engine_version: str | None
    alternatives_considered: list[dict[str, object]]
    trust_status: str
    readiness_status: str
    evaluated_readiness_level: str | None
    readiness_mapping_policy_code: str | None
    readiness_mapping_policy_version: str | None
    warnings: list[str]
    sufficiency_status: SufficiencyStatus
    escalation_status: EscalationStatus
    decision: str
    decision_reason_code: str
    decision_summary: str
    policy_code: str
    policy_version: str
    content_hash: str
    decided_at: datetime


class OrchestrationStepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    step_sequence: int
    analytical_level: str | None
    engine_code: str | None
    engine_version: str | None
    step_type: OrchestrationStepType
    status: str
    started_at: datetime
    completed_at: datetime | None
    source_execution_id: UUID | None
    source_result_id: UUID | None
    result_locator: str | None
    output_index: int | None
    finding_id: UUID | None
    input_reference_summary: dict[str, object]
    output_reference_summary: dict[str, object]
    warnings: list[str]
    limitations: list[str]
    block_reason_code: str | None
    error_code: str | None
    content_hash: str


class OrchestrationHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    transition_sequence: int
    previous_status: str | None
    new_status: OrchestrationStatusValue
    reason_code: str
    changed_by_user_id: UUID
    changed_at: datetime
    metadata_json: dict[str, object]


class OrchestrationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    request_code: str
    correlation_id: str
    idempotency_key: str
    definition_code: str
    definition_version: str
    requested_analytical_level: str | None
    dataset_id: UUID
    dataset_version_id: UUID | None
    dataset_reference: str
    trust_assessment_id: UUID
    analytical_readiness_id: UUID
    requested_by_user_id: UUID
    requested_at: datetime
    status: OrchestrationStatusValue
    publish_finding: bool
    parameters_summary: dict[str, object]
    request_context: dict[str, object]
    context_fingerprint: str
    warnings: list[str]
    limitations: list[str]
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class OrchestrationDetail(OrchestrationRead):
    decisions: list[OrchestrationDecisionRead]
    steps: list[OrchestrationStepRead]
    history: list[OrchestrationHistoryRead]


class OrchestrationPage(BaseModel):
    items: list[OrchestrationRead]
    page: int
    page_size: int
    total: int


class EngineRegistrationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    engine_code: str
    engine_name: str
    engine_version: str
    analytical_level: OrchestrationAnalyticalLevel
    capability_code: str
    status: str
    is_available: bool
    supports_sync: bool
    supports_async: bool
    input_contract_version: str
    output_contract_version: str
    implementation_reference: str
