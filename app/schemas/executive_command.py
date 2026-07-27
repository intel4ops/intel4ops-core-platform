from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class CurrencyExecutiveSummary(BaseModel):
    currency_code: str
    exposure: Decimal
    addressable_exposure: Decimal
    expected_recoverable_value: Decimal
    realized_value: Decimal
    verified_value: Decimal
    adjustments: Decimal
    reversals: Decimal


class AttentionItem(BaseModel):
    item_type: str
    item_id: UUID
    reason: str
    priority: str
    value: Decimal | None
    currency_code: str | None
    owner_user_id: UUID | None
    status: str
    next_action: str
    evidence_reference: str | None


class ExecutiveSummary(BaseModel):
    period_start: datetime
    period_end: datetime
    currencies: list[CurrencyExecutiveSummary]
    active_recovery_cases: int
    overdue_actions: int
    unresolved_critical_findings: int
    value_awaiting_verification: dict[str, Decimal]
    data_confidence_status: str
    top_attention_items: list[AttentionItem]


class RecoveryPortfolio(BaseModel):
    by_stage: dict[str, int]
    by_owner: dict[str, int]
    overdue_actions: int
    blocked_cases: int
    verification_backlog: int


class TrendPoint(BaseModel):
    period: str
    currency_code: str
    measure: str
    value: Decimal
