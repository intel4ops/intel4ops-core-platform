from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.entities import portable_json, utc_now


class RecoveryCase(Base):
    __tablename__ = "recovery_cases"
    __table_args__ = (
        UniqueConstraint("organization_id", "idempotency_key", name="uq_recovery_case_idempotency"),
        Index("ix_recovery_case_org_status", "organization_id", "status"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    opportunity_id: Mapped[UUID] = mapped_column(
        ForeignKey("recovery_opportunities.id", ondelete="RESTRICT")
    )
    baseline_id: Mapped[UUID] = mapped_column(
        ForeignKey("economic_baseline_versions.id", ondelete="RESTRICT")
    )
    case_code: Mapped[str] = mapped_column(String(40), unique=True)
    idempotency_key: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(250))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="approved")
    currency_code: Mapped[str] = mapped_column(String(3))
    expected_value: Mapped[Decimal] = mapped_column(Numeric(38, 12))
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class RecoveryExecution(Base):
    __tablename__ = "recovery_executions"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "idempotency_key", name="uq_recovery_execution_idempotency"
        ),
        Index("ix_recovery_execution_org_case", "organization_id", "recovery_case_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    recovery_case_id: Mapped[UUID] = mapped_column(
        ForeignKey("recovery_cases.id", ondelete="RESTRICT")
    )
    action_id: Mapped[UUID] = mapped_column(
        ForeignKey("operational_actions.id", ondelete="RESTRICT")
    )
    idempotency_key: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(40), default="planned")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    execution_notes: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class RecoveryValueMeasurement(Base):
    __tablename__ = "recovery_value_measurements"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "idempotency_key", name="uq_recovery_measurement_idempotency"
        ),
        Index("ix_recovery_measurement_org_execution", "organization_id", "execution_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    execution_id: Mapped[UUID] = mapped_column(
        ForeignKey("recovery_executions.id", ondelete="RESTRICT")
    )
    idempotency_key: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(40), default="draft")
    baseline_amount: Mapped[Decimal] = mapped_column(Numeric(38, 12))
    actual_amount: Mapped[Decimal] = mapped_column(Numeric(38, 12))
    realized_value: Mapped[Decimal] = mapped_column(Numeric(38, 12))
    currency_code: Mapped[str] = mapped_column(String(3))
    measurement_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    measurement_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    methodology: Mapped[str] = mapped_column(String(100))
    calculation_inputs: Mapped[dict[str, object]] = mapped_column(portable_json)
    limitations: Mapped[list[str]] = mapped_column(portable_json, default=list)
    submitted_by_user_id: Mapped[UUID | None] = mapped_column(Uuid)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class RecoveryEvidenceLink(Base):
    __tablename__ = "recovery_evidence_links"
    __table_args__ = (
        Index("ix_recovery_evidence_org_measurement", "organization_id", "measurement_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    measurement_id: Mapped[UUID] = mapped_column(
        ForeignKey("recovery_value_measurements.id", ondelete="CASCADE")
    )
    evidence_type: Mapped[str] = mapped_column(String(50))
    source_type: Mapped[str] = mapped_column(String(50))
    source_identifier: Mapped[str] = mapped_column(String(500))
    integrity_fingerprint: Mapped[str | None] = mapped_column(String(128))
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class RecoveryFinanceVerification(Base):
    __tablename__ = "recovery_finance_verifications"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "idempotency_key", name="uq_recovery_verification_idempotency"
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    measurement_id: Mapped[UUID] = mapped_column(
        ForeignKey("recovery_value_measurements.id", ondelete="RESTRICT")
    )
    idempotency_key: Mapped[str] = mapped_column(String(255))
    decision: Mapped[str] = mapped_column(String(30))
    verified_amount: Mapped[Decimal] = mapped_column(Numeric(38, 12))
    currency_code: Mapped[str] = mapped_column(String(3))
    rationale: Mapped[str] = mapped_column(Text)
    reviewer_user_id: Mapped[UUID] = mapped_column(Uuid)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class VerifiedValueLedgerEntry(Base):
    __tablename__ = "verified_value_ledger_entries"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "idempotency_key", name="uq_verified_ledger_idempotency"
        ),
        UniqueConstraint(
            "recovery_case_id", "entry_sequence", name="uq_verified_ledger_case_sequence"
        ),
        CheckConstraint("amount <> 0", name="ck_verified_ledger_nonzero"),
        Index(
            "ix_verified_ledger_org_case_currency",
            "organization_id",
            "recovery_case_id",
            "currency_code",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    recovery_case_id: Mapped[UUID] = mapped_column(
        ForeignKey("recovery_cases.id", ondelete="RESTRICT")
    )
    measurement_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("recovery_value_measurements.id", ondelete="RESTRICT")
    )
    verification_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("recovery_finance_verifications.id", ondelete="RESTRICT")
    )
    reversal_of_ledger_entry_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "verified_value_ledger_entries.id",
            name="fk_verified_ledger_reversal_of",
            ondelete="CASCADE",
        )
    )
    adjustment_of_ledger_entry_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "verified_value_ledger_entries.id",
            name="fk_verified_ledger_adjustment_of",
            ondelete="CASCADE",
        )
    )
    entry_sequence: Mapped[int] = mapped_column(Integer)
    entry_type: Mapped[str] = mapped_column(String(40))
    amount: Mapped[Decimal] = mapped_column(Numeric(38, 12))
    currency_code: Mapped[str] = mapped_column(String(3))
    idempotency_key: Mapped[str] = mapped_column(String(255))
    reason: Mapped[str] = mapped_column(Text)
    entry_hash: Mapped[str] = mapped_column(String(64), unique=True)
    posted_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


@event.listens_for(VerifiedValueLedgerEntry, "before_update")
@event.listens_for(VerifiedValueLedgerEntry, "before_delete")
def _prevent_posted_ledger_mutation(*_: object) -> None:
    raise ValueError("posted ledger entries are immutable")


class RecoveryAuditEvent(Base):
    __tablename__ = "recovery_audit_events"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "idempotency_key", name="uq_recovery_audit_idempotency"
        ),
        Index("ix_recovery_audit_org_case", "organization_id", "recovery_case_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    recovery_case_id: Mapped[UUID] = mapped_column(
        ForeignKey("recovery_cases.id", ondelete="RESTRICT")
    )
    event_type: Mapped[str] = mapped_column(String(60))
    actor_user_id: Mapped[UUID] = mapped_column(Uuid)
    idempotency_key: Mapped[str] = mapped_column(String(255))
    reason: Mapped[str] = mapped_column(Text)
    event_payload: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
