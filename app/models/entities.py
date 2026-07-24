from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class OrganizationStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class MembershipRole(StrEnum):
    PLATFORM_ADMIN = "platform_admin"
    ORGANIZATION_ADMIN = "organization_admin"
    ANALYST = "analyst"
    OPERATOR = "operator"
    RECOVERY_MANAGER = "recovery_manager"
    VIEWER = "viewer"


class MembershipStatus(StrEnum):
    INVITED = "invited"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


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
    memberships: Mapped[list[OrganizationMembership]] = relationship(
        back_populates="organization", cascade="all, delete-orphan", passive_deletes=True
    )


class OrganizationMembership(Base):
    __tablename__ = "organization_members"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "user_id",
            name="uq_organization_members_organization_user",
        ),
        CheckConstraint(
            "role IN ('platform_admin', 'organization_admin', 'analyst', 'operator', "
            "'recovery_manager', 'viewer')",
            name="ck_organization_members_role",
        ),
        CheckConstraint(
            "status IN ('invited', 'active', 'suspended', 'revoked')",
            name="ck_organization_members_status",
        ),
        Index("ix_organization_members_organization_id", "organization_id"),
        Index("ix_organization_members_user_id", "user_id"),
        Index("ix_organization_members_role", "role"),
        Index("ix_organization_members_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    user_id: Mapped[UUID] = mapped_column(Uuid)
    role: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), default=MembershipStatus.INVITED.value)
    invited_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    organization: Mapped[Organization] = relationship(back_populates="memberships")


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
