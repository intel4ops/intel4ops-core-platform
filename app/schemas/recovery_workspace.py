from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.actions import ActionRead
from app.schemas.decision_intelligence import (
    DecisionApprovalRead,
    DecisionWorkspaceRecommendationRead,
)
from app.schemas.recovery_ledger import CaseRead, ExecutionRead, LedgerRead, MeasurementRead


class RecoveryWorkspaceActionEvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    lifecycle_stage: str
    evidence_type: str
    source_type: str
    source_identifier: str
    document_reference: str | None
    measurement_value: Decimal | None
    measurement_unit: str | None
    observed_at: datetime | None
    actor_user_id: UUID
    notes: str | None
    metadata_json: dict[str, object]
    integrity_fingerprint: str | None
    created_at: datetime


class RecoveryWorkspaceActionOutcomeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    outcome_type: str
    avoided_cost: Decimal | None
    intervention_cost: Decimal | None
    downtime_avoided: Decimal | None
    production_preserved: Decimal | None
    risk_reduction: Decimal | None
    currency_code: str | None
    confidence_score: Decimal | None
    calculation_method: str
    verification_method: str | None
    verified_by_user_id: UUID | None
    verified_at: datetime | None
    assumptions: list[str]
    limitations: list[str]
    created_at: datetime


class RecoveryWorkspaceActionEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_type: str
    prior_status: str | None
    new_status: str | None
    actor_user_id: UUID
    actor_role: str
    reason_code: str
    note: str | None
    metadata_json: dict[str, object]
    occurred_at: datetime


class RecoveryWorkspaceEvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    measurement_id: UUID
    evidence_type: str
    source_type: str
    source_identifier: str
    integrity_fingerprint: str | None
    observed_at: datetime | None
    created_by_user_id: UUID
    created_at: datetime


class RecoveryWorkspaceVerificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    measurement_id: UUID
    decision: str
    verified_amount: Decimal
    currency_code: str
    rationale: str
    reviewer_user_id: UUID
    reviewed_at: datetime


class RecoveryWorkspaceAuditEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_type: str
    actor_user_id: UUID
    reason: str
    event_payload: dict[str, object]
    occurred_at: datetime


class RecoveryWorkspaceRead(BaseModel):
    finding_id: UUID
    recommendation: DecisionWorkspaceRecommendationRead | None
    approval: DecisionApprovalRead | None
    action: ActionRead | None
    action_evidence: list[RecoveryWorkspaceActionEvidenceRead]
    action_outcomes: list[RecoveryWorkspaceActionOutcomeRead]
    action_history: list[RecoveryWorkspaceActionEventRead]
    recovery_case: CaseRead | None
    recovery_execution: ExecutionRead | None
    measurements: list[MeasurementRead]
    measurement_evidence: list[RecoveryWorkspaceEvidenceRead]
    latest_verification: RecoveryWorkspaceVerificationRead | None
    verification_history: list[RecoveryWorkspaceVerificationRead]
    verified_ledger: list[LedgerRead]
    recovery_history: list[RecoveryWorkspaceAuditEventRead]
