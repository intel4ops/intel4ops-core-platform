from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class CanonicalRecord(BaseModel):
    type: str = Field(
        pattern=r"^(customer|resource|job|time_entry|material|expense|documentation|invoice|invoice_line|payment|payment_allocation|contract)$"
    )
    id: str = Field(min_length=1, max_length=120)
    data: dict[str, object] = Field(default_factory=dict)

    def engine_record(self) -> dict[str, object]:
        return {"type": self.type, "id": self.id, **self.data}


class JobToCashRunCreate(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=255)
    source_system_id: UUID | None = None
    currency_code: str = Field(pattern=r"^[A-Z]{3}$")
    as_of: date
    records: list[CanonicalRecord] = Field(min_length=1, max_length=1000)


class LeakageRead(BaseModel):
    code: str
    job_id: str
    exposure: Decimal
    reason: str
    evidence_ids: list[str]


class JobToCashRunRead(BaseModel):
    id: UUID
    organization_id: UUID
    status: str
    currency_code: str
    findings: list[LeakageRead]
    source_totals: dict[str, object]
    reconciliation: dict[str, object]
    created_at: datetime
