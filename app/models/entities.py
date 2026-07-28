from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING
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
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.source_system import SourceSystem


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
    DRAFT = "draft"
    PUBLISHED = "published"
    UNDER_REVIEW = "under_review"
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"
    SUPERSEDED = "superseded"
    RESOLVED = "resolved"
    ARCHIVED = "archived"
    OPEN = "open"
    ACCEPTED = "accepted"
    IN_RECOVERY = "in_recovery"
    VERIFIED = "verified"


portable_json = JSON().with_variant(
    postgresql.JSONB(astext_type=Text()),
    "postgresql",
)


class Organization(Base):
    __tablename__ = "organizations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'inactive')",
            name="ck_organizations_status",
        ),
    )

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
    source_systems: Mapped[list[SourceSystem]] = relationship(back_populates="organization")


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
    __table_args__ = (
        Index(
            "uq_findings_organization_deduplication",
            "organization_id",
            "deduplication_key",
            unique=True,
        ),
        CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)",
            name="ck_findings_confidence_score",
        ),
        CheckConstraint(
            "affected_record_count >= 0",
            name="ck_findings_affected_record_count",
        ),
        CheckConstraint(
            "severity IN ('info', 'low', 'medium', 'high', 'critical')",
            name="ck_findings_severity",
        ),
        CheckConstraint(
            "status IN ('draft', 'published', 'under_review', 'confirmed', "
            "'dismissed', 'superseded', 'resolved', 'archived', 'open', "
            "'accepted', 'in_recovery', 'verified')",
            name="ck_findings_status",
        ),
        Index("ix_findings_organization_status", "organization_id", "status"),
        Index("ix_findings_organization_type", "organization_id", "finding_type"),
        Index("ix_findings_organization_severity", "organization_id", "severity"),
        Index("ix_findings_organization_detected", "organization_id", "detected_at"),
        Index("ix_findings_organization_occurrence", "organization_id", "occurrence_start"),
        Index("ix_findings_source_execution", "organization_id", "source_execution_id"),
        Index(
            "ix_findings_definition",
            "organization_id",
            "definition_code",
            "definition_version",
        ),
        Index(
            "ix_findings_oikb_definition",
            "organization_id",
            "oikb_definition_id",
            "oikb_definition_version_id",
        ),
        Index(
            "ix_findings_org_signature",
            "organization_id",
            "signature_version_id",
        ),
    )

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
    confidence_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0"))
    status: Mapped[str] = mapped_column(String(50), default=FindingStatus.OPEN.value)
    ontology_concept_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    causal_chain_id: Mapped[str | None] = mapped_column(String, nullable=True)
    first_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    finding_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    finding_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    domain_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    process_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    industry_pack_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    severity_reason: Mapped[dict[str, object] | None] = mapped_column(portable_json, nullable=True)
    confidence_level: Mapped[str | None] = mapped_column(String(30), nullable=True)
    confidence_method_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    confidence_method_version: Mapped[str | None] = mapped_column(String(30), nullable=True)
    confidence_components: Mapped[dict[str, object] | None] = mapped_column(
        portable_json, nullable=True
    )
    confidence_interpretation: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_limitations: Mapped[list[str] | None] = mapped_column(portable_json, nullable=True)
    measured_value: Mapped[Decimal | None] = mapped_column(Numeric(38, 12), nullable=True)
    measured_value_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    measured_unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    measured_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    exposure_value: Mapped[Decimal | None] = mapped_column(Numeric(38, 12), nullable=True)
    exposure_value_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    exposure_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    affected_record_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    occurrence_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    occurrence_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_by_finding_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("findings.id", ondelete="RESTRICT"), nullable=True
    )
    source_execution_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("intelligence_executions.id", ondelete="RESTRICT"), nullable=True
    )
    source_result_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("intelligence_executions.id", ondelete="RESTRICT"), nullable=True
    )
    definition_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    definition_version: Mapped[str | None] = mapped_column(String(30), nullable=True)
    definition_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    oikb_definition_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("oikb_definitions.id", ondelete="RESTRICT"), nullable=True
    )
    oikb_definition_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("oikb_definition_versions.id", ondelete="RESTRICT"), nullable=True
    )
    signature_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("operational_signature_versions.id", ondelete="RESTRICT"), nullable=True
    )
    signature_execution_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "operational_signature_executions.id",
            name="fk_findings_signature_execution_id",
            ondelete="SET NULL",
            use_alter=True,
        ),
        nullable=True,
    )
    trust_assessment_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("trust_assessments.id", ondelete="RESTRICT"), nullable=True
    )
    analytical_readiness_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("analytical_readiness_decisions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    dataset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("datasets.id", ondelete="RESTRICT"), nullable=True
    )
    dataset_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    warnings: Mapped[list[str] | None] = mapped_column(portable_json, nullable=True)
    limitations: Mapped[list[str] | None] = mapped_column(portable_json, nullable=True)
    content_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    deduplication_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    updated_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

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
    __table_args__ = (
        CheckConstraint(
            "status IN ('planned')",
            name="ck_recovery_actions_status",
        ),
    )

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
