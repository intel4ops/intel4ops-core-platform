from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.entities import portable_json, utc_now


class ApplicationClient(Base):
    __tablename__ = "application_clients"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    client_code: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(150))
    client_type: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="active")
    metadata_json: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ApiRequestAuditEvent(Base):
    __tablename__ = "api_request_audit_events"
    __table_args__ = (
        UniqueConstraint("organization_id", "request_id", name="uq_api_audit_org_request"),
        Index("ix_api_audit_org_time", "organization_id", "occurred_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    request_id: Mapped[str] = mapped_column(String(100))
    correlation_id: Mapped[str] = mapped_column(String(100))
    client_code: Mapped[str] = mapped_column(String(80))
    actor_user_id: Mapped[UUID] = mapped_column(Uuid)
    operation: Mapped[str] = mapped_column(String(120))
    outcome: Mapped[str] = mapped_column(String(30))
    status_code: Mapped[int] = mapped_column(Integer)
    details: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class JobToCashRun(Base):
    __tablename__ = "job_to_cash_runs"
    __table_args__ = (
        UniqueConstraint("organization_id", "idempotency_key", name="uq_j2c_run_idempotency"),
        Index("ix_j2c_run_org_time", "organization_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    source_system_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("source_systems.id", ondelete="RESTRICT")
    )
    idempotency_key: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(30))
    currency_code: Mapped[str] = mapped_column(String(3))
    source_totals: Mapped[dict[str, object]] = mapped_column(portable_json)
    reconciliation: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class JobToCashRecord(Base):
    __tablename__ = "job_to_cash_records"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "run_id", "record_type", "external_id", name="uq_j2c_record"
        ),
        Index("ix_j2c_record_org_type", "organization_id", "record_type"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    run_id: Mapped[UUID] = mapped_column(ForeignKey("job_to_cash_runs.id", ondelete="CASCADE"))
    record_type: Mapped[str] = mapped_column(String(40))
    external_id: Mapped[str] = mapped_column(String(120))
    source_reference: Mapped[str] = mapped_column(String(500))
    integrity_fingerprint: Mapped[str] = mapped_column(String(64))
    canonical_data: Mapped[dict[str, object]] = mapped_column(portable_json)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
