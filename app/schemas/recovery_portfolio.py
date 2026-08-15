from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class PortfolioCurrencyValue(BaseModel):
    currency_code: str
    expected_value: Decimal
    realized_value: Decimal
    verified_value: Decimal


class RecoveryPortfolioSummary(BaseModel):
    finding_count: int
    active_recovery_count: int
    overdue_count: int
    awaiting_verification_count: int
    disputed_or_rejected_verification_count: int
    value_by_currency: list[PortfolioCurrencyValue]


class RecoveryPortfolioPipeline(BaseModel):
    approved_no_action: int
    action_active: int
    execution_active: int
    outcome_recorded: int
    measurement_pending: int
    verification_pending: int
    verification_attention: int
    verified: int
    closed: int


class RecoveryPortfolioItem(BaseModel):
    finding_id: UUID
    finding_title: str
    finding_summary: str
    finding_status: str
    finding_domain: str
    recommendation_id: UUID
    approval_id: UUID | None
    approval_decision: str | None
    action_id: UUID | None
    action_status: str | None
    assigned_user_id: UUID | None
    assigned_role: str | None
    due_at: datetime | None
    action_created_at: datetime | None
    action_completed_at: datetime | None
    recovery_case_id: UUID | None
    recovery_case_status: str | None
    recovery_execution_id: UUID | None
    recovery_execution_status: str | None
    execution_started_at: datetime | None
    execution_completed_at: datetime | None
    outcome_id: UUID | None
    outcome_type: str | None
    measurement_id: UUID | None
    measurement_status: str | None
    measurement_submitted_at: datetime | None
    verification_id: UUID | None
    verification_decision: str | None
    verification_reviewer_user_id: UUID | None
    verification_rationale: str | None
    verification_reviewed_at: datetime | None
    ledger_entry_id: UUID | None
    ledger_posted_at: datetime | None
    currency_code: str | None
    expected_value: Decimal | None
    realized_value: Decimal | None
    verified_value: Decimal | None
    stage: str
    overdue: bool
    attention_required: bool
    last_activity_at: datetime


class RecoveryPortfolioPagination(BaseModel):
    page: int
    page_size: int
    total: int


class RecoveryPortfolioRead(BaseModel):
    organization_id: UUID
    summary: RecoveryPortfolioSummary
    pipeline: RecoveryPortfolioPipeline
    items: list[RecoveryPortfolioItem]
    pagination: RecoveryPortfolioPagination
