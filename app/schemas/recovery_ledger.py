from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.engines.recovery_ledger_engine import LedgerEntryType, ValueCategory


class CaseCreate(BaseModel):
    opportunity_id: UUID
    baseline_id: UUID
    idempotency_key: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=250)
    description: str = Field(min_length=1, max_length=4000)


class CaseUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=250)
    description: str | None = Field(default=None, min_length=1, max_length=4000)
    status: str | None = Field(default=None, pattern=r"^(approved|active|completed|closed)$")


class CaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    opportunity_id: UUID
    baseline_id: UUID
    case_code: str
    title: str
    description: str
    status: str
    currency_code: str
    expected_value: Decimal
    created_at: datetime
    updated_at: datetime


class ExecutionCreate(BaseModel):
    action_id: UUID
    idempotency_key: str = Field(min_length=1, max_length=255)
    execution_notes: str | None = Field(default=None, max_length=4000)


class ExecutionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    recovery_case_id: UUID
    action_id: UUID
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    execution_notes: str | None


class EvidenceCreate(BaseModel):
    evidence_type: str = Field(min_length=1, max_length=50)
    source_type: str = Field(min_length=1, max_length=50)
    source_identifier: str = Field(min_length=1, max_length=500)
    integrity_fingerprint: str | None = Field(default=None, max_length=128)
    observed_at: datetime | None = None


class MeasurementCreate(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=255)
    category: ValueCategory
    baseline_amount: Decimal
    actual_amount: Decimal
    currency_code: str = Field(pattern=r"^[A-Z]{3}$")
    measurement_start: datetime
    measurement_end: datetime
    methodology: str = Field(min_length=1, max_length=100)
    calculation_inputs: dict[str, object] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    evidence: list[EvidenceCreate] = Field(min_length=1)

    @model_validator(mode="after")
    def period_is_ordered(self) -> "MeasurementCreate":
        if self.measurement_end <= self.measurement_start:
            raise ValueError("measurement_end must be after measurement_start")
        return self


class MeasurementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    execution_id: UUID
    category: ValueCategory
    status: str
    baseline_amount: Decimal
    actual_amount: Decimal
    realized_value: Decimal
    currency_code: str
    measurement_start: datetime
    measurement_end: datetime
    methodology: str
    calculation_inputs: dict[str, object]
    limitations: list[str]
    submitted_by_user_id: UUID | None
    submitted_at: datetime | None


class VerifyCreate(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=255)
    verified_amount: Decimal = Field(gt=0)
    currency_code: str = Field(pattern=r"^[A-Z]{3}$")
    rationale: str = Field(min_length=1, max_length=4000)


class FinanceReviewCreate(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=255)
    decision: str = Field(pattern=r"^(needs_information|rejected)$")
    rationale: str = Field(min_length=1, max_length=4000)


class LedgerMutationCreate(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=255)
    amount: Decimal = Field(gt=0)
    reason: str = Field(min_length=1, max_length=4000)
    direction: str | None = Field(default=None, pattern=r"^(positive|negative)$")


class LedgerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    recovery_case_id: UUID
    measurement_id: UUID | None
    verification_id: UUID | None
    reversal_of_ledger_entry_id: UUID | None
    adjustment_of_ledger_entry_id: UUID | None
    entry_sequence: int
    entry_type: LedgerEntryType
    amount: Decimal
    currency_code: str
    reason: str
    entry_hash: str
    posted_by_user_id: UUID
    posted_at: datetime


class LedgerPage(BaseModel):
    items: list[LedgerRead]
    page: int
    page_size: int
    total: int


class CurrencyValue(BaseModel):
    currency_code: str
    expected_value: Decimal
    realized_value: Decimal
    verified_value: Decimal
    net_verified_value: Decimal


class ValueSummary(BaseModel):
    recovery_case_id: UUID
    currencies: list[CurrencyValue]
