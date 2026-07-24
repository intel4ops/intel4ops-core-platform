from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class OrganizationStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class FindingStatus(StrEnum):
    OPEN = "open"
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"
    IN_RECOVERY = "in_recovery"
    VERIFIED = "verified"


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    legal_name: Mapped[str | None] = mapped_column(String(250), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country_code: Mapped[str] = mapped_column(String(2))
    default_currency: Mapped[str] = mapped_column(String(3))
    timezone: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default=OrganizationStatus.ACTIVE.value)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    findings: Mapped[list[Finding]] = relationship(back_populates="organization")


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    rule_id: Mapped[str] = mapped_column(String, index=True)
    title: Mapped[str] = mapped_column(String(250))
    summary: Mapped[str] = mapped_column(Text)
    domain: Mapped[str] = mapped_column(String(100), index=True)
    severity: Mapped[str] = mapped_column(String(50), default="medium")
    priority: Mapped[int] = mapped_column(Integer, default=3)
    exposure_low: Mapped[float] = mapped_column(Float, default=0)
    exposure_high: Mapped[float] = mapped_column(Float, default=0)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    confidence_score: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(50), default=FindingStatus.OPEN.value)
    ontology_concept_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    causal_chain_id: Mapped[str | None] = mapped_column(String, nullable=True)
    first_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    organization: Mapped[Organization] = relationship(back_populates="findings")
    evidence: Mapped[list[FindingEvidence]] = relationship(
        back_populates="finding", cascade="all, delete-orphan"
    )
    recovery_actions: Mapped[list[RecoveryAction]] = relationship(
        back_populates="finding", cascade="all, delete-orphan"
    )


class FindingEvidence(Base):
    __tablename__ = "finding_evidence"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    finding_id: Mapped[UUID] = mapped_column(
        ForeignKey("findings.id", ondelete="CASCADE"), index=True
    )
    source_system: Mapped[str] = mapped_column(String(100))
    source_record_id: Mapped[str] = mapped_column(String(150))
    evidence_type: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict[str, object]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    finding: Mapped[Finding] = relationship(back_populates="evidence")


class RecoveryAction(Base):
    __tablename__ = "recovery_actions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    finding_id: Mapped[UUID] = mapped_column(
        ForeignKey("findings.id", ondelete="RESTRICT"), index=True
    )
    title: Mapped[str] = mapped_column(String(250))
    owner: Mapped[str] = mapped_column(String(150))
    status: Mapped[str] = mapped_column(String(50), default="planned")
    expected_recovery: Mapped[float] = mapped_column(Float, default=0)
    measured_recovery: Mapped[float] = mapped_column(Float, default=0)
    verified_recovery: Mapped[float] = mapped_column(Float, default=0)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    finding: Mapped[Finding] = relationship(back_populates="recovery_actions")
