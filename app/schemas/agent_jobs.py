"""AGENTIC-CONTROL-001 Phase C/G: the EvidencePackage contract and the
structured worker-output contract. Agents never receive a raw
conversation history or an entire prompt transcript -- they receive one
compressed EvidencePackage and must return one validated
WorkerStructuredResult. Arbitrary prose is never the machine contract."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GapClass(StrEnum):
    """Phase J's reusable-gap taxonomy. Mapped (not duplicated) onto this
    program's pre-existing simulation-gap-ledger classification for
    continuity -- see docs/agent-routing-policy.md's mapping table:
    DATA_CONTRACT_GAP ~ DATA_CONTRACT_LIMITATION, GOVERNED_POLICY_GAP ~
    GOVERNANCE_GAP, INTELLIGENCE_CAPABILITY_GAP ~ CAPABILITY_MODEL_GAP,
    ORCHESTRATION_RUNTIME_GAP is the RUN-RELIABILITY-001 classification
    introduced this program, carried over verbatim."""

    DATA_CONTRACT_GAP = "DATA_CONTRACT_GAP"
    EXTRACTION_GAP = "EXTRACTION_GAP"
    SEMANTIC_GAP = "SEMANTIC_GAP"
    MAPPING_GAP = "MAPPING_GAP"
    ENTITY_RELATIONSHIP_GAP = "ENTITY_RELATIONSHIP_GAP"
    PROCESS_MODEL_GAP = "PROCESS_MODEL_GAP"
    GOVERNED_POLICY_GAP = "GOVERNED_POLICY_GAP"
    INTELLIGENCE_CAPABILITY_GAP = "INTELLIGENCE_CAPABILITY_GAP"
    ECONOMIC_VALUE_GAP = "ECONOMIC_VALUE_GAP"
    ORCHESTRATION_RUNTIME_GAP = "ORCHESTRATION_RUNTIME_GAP"


class EvidenceObservation(BaseModel):
    observed_behavior: str
    expected_capability_behavior: str | None = None


class EvidenceImpact(BaseModel):
    affected_items: int = 0
    affected_economic_value: Decimal | None = None
    currency: str | None = None
    simulations_affected: int = 0


class EvidenceEvidence(BaseModel):
    source_artifact_refs: list[str] = Field(default_factory=list)
    production_output_refs: list[str] = Field(default_factory=list)
    canonical_entities: list[str] = Field(default_factory=list)
    relationships: list[str] = Field(default_factory=list)
    mappings: list[str] = Field(default_factory=list)
    readiness_evidence: list[str] = Field(default_factory=list)
    source_record_refs: list[str] = Field(default_factory=list)


class EvidenceControl(BaseModel):
    existing_capabilities: list[str] = Field(default_factory=list)
    prior_related_gaps: list[str] = Field(default_factory=list)
    prior_remediation: list[str] = Field(default_factory=list)
    regression_status: str | None = None


class EvidenceSafety(BaseModel):
    fp_exposure: Literal["low", "medium", "high", "unknown"] = "unknown"
    truth_isolation_constraints: str | None = None
    policy_dependencies: list[str] = Field(default_factory=list)
    data_contract_limitations: list[str] = Field(default_factory=list)


class EvidenceCodeContext(BaseModel):
    relevant_files: list[str] = Field(default_factory=list)
    relevant_modules: list[str] = Field(default_factory=list)
    known_tests: list[str] = Field(default_factory=list)


class EvidencePackage(BaseModel):
    """The one canonical contract a worker (local or premium) receives.
    Never a conversation history. `evidence_plane` gates what this
    package is allowed to contain -- see
    app.models.agent_jobs.AgentJobEvidencePlane and
    app.services.agent_job_service.create_job's enforcement of it."""

    model_config = ConfigDict(frozen=True)

    work_item_id: str
    evidence_plane: Literal["production", "validation"]
    simulation_ids: list[str] = Field(default_factory=list)
    analysis_case_ids: list[str] = Field(default_factory=list)
    run_ids: list[str] = Field(default_factory=list)
    gap_id: str | None = None
    risk_class: Literal["R0", "R1", "R2", "R3"]

    observation: EvidenceObservation
    impact: EvidenceImpact
    evidence: EvidenceEvidence
    control: EvidenceControl
    safety: EvidenceSafety
    code_context: EvidenceCodeContext
    question: str


class WorkerStructuredResult(BaseModel):
    """Phase G's required machine contract. Validated server-side;
    malformed output is never silently accepted -- see
    app.services.agent_job_service.submit_result."""

    primary_gap_class: GapClass
    secondary_gap_classes: list[GapClass] = Field(default_factory=list)
    confidence: int = Field(ge=0, le=100)
    summary: str = Field(min_length=1, max_length=4000)
    evidence_refs: list[str] = Field(default_factory=list)
    fp_risk: Literal["low", "medium", "high"]
    architecture_impact: bool
    policy_dependency: bool
    data_contract_dependency: bool
    recommended_action: str = Field(min_length=1, max_length=2000)
    escalate: bool
    escalation_reason: str | None = None

    @model_validator(mode="after")
    def _escalation_reason_required_when_escalating(self) -> WorkerStructuredResult:
        if self.escalate and not (self.escalation_reason or "").strip():
            raise ValueError("escalation_reason is required when escalate is true")
        return self


class AgentJobCreate(BaseModel):
    job_type: str
    risk_class: Literal["R0", "R1", "R2", "R3"]
    requested_capability: str
    evidence_plane: Literal["production", "validation"] = "production"
    analysis_case_id: UUID | None = None
    run_id: UUID | None = None
    simulation_id: str | None = None
    gap_id: str | None = None
    parent_job_id: UUID | None = None
    priority: int = 0
    evidence_package: EvidencePackage
    client_idempotency_key: str | None = None


class AgentJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID | None
    analysis_case_id: UUID | None
    run_id: UUID | None
    simulation_id: str | None
    gap_id: str | None
    parent_job_id: UUID | None
    job_type: str
    risk_class: str
    status: str
    priority: int
    evidence_plane: str
    requested_capability: str
    assigned_worker: str | None
    assigned_model: str | None
    model_version: str | None
    prompt_template_version: str | None
    input_evidence_ref: str | None
    result_ref: str | None
    confidence: int | None
    escalation_reason: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    failed_at: datetime | None
    retry_count: int
    execution_time_ms: int | None
    input_tokens: int | None
    output_tokens: int | None
    reasoning_tokens: int | None
    estimated_cost: Decimal | None
    actual_cost: Decimal | None
    error_code: str | None
    error_detail: str | None
    owner_approval_required: bool
    owner_approval_status: str


class AgentJobClaimResponse(BaseModel):
    job: AgentJobRead
    lease_id: UUID
    evidence_package: EvidencePackage
    model_profile: str
    model_identifier: str
    model_parameters: dict


class AgentJobHeartbeatRequest(BaseModel):
    lease_id: UUID


class AgentJobResultSubmit(BaseModel):
    lease_id: UUID
    structured_result: WorkerStructuredResult
    execution_time_ms: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    reasoning_tokens: int = Field(ge=0, default=0)
    ttft_ms: int | None = Field(default=None, ge=0)
    tokens_per_second: float | None = None
    model_identifier: str


class AgentJobFailureSubmit(BaseModel):
    lease_id: UUID
    error_code: str
    error_detail: str
    retryable: bool = True


class OwnerApprovalDecision(BaseModel):
    approve: bool
    note: str | None = None
