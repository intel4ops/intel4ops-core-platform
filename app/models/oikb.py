from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.entities import utc_now
from app.models.source_system import portable_json


class OIKBDefinition(Base):
    __tablename__ = "oikb_definitions"
    __table_args__ = (
        UniqueConstraint(
            "stable_code",
            "scope_key",
            name="uq_oikb_definition_scope",
        ),
        CheckConstraint(
            "scope_type IN ('shared_core','industry','regional','organization')",
            name="ck_oikb_definition_scope_type",
        ),
        Index("ix_oikb_definition_code", "stable_code"),
        Index("ix_oikb_definition_owner", "owner_organization_id"),
        Index("ix_oikb_definition_resolution", "stable_code", "scope_type"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    stable_code: Mapped[str] = mapped_column(String(150))
    name: Mapped[str] = mapped_column(String(250))
    description: Mapped[str] = mapped_column(Text)
    knowledge_class: Mapped[str] = mapped_column(String(50))
    analytical_level: Mapped[str] = mapped_column(String(30))
    domain: Mapped[str] = mapped_column(String(100))
    subdomain: Mapped[str | None] = mapped_column(String(100), nullable=True)
    owner_organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=True
    )
    industry_pack_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    region_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    scope_type: Mapped[str] = mapped_column(String(30))
    scope_key: Mapped[str] = mapped_column(String(180))
    is_system_definition: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    versions: Mapped[list[OIKBDefinitionVersion]] = relationship(
        back_populates="definition", cascade="all, delete-orphan"
    )


class OIKBDefinitionVersion(Base):
    __tablename__ = "oikb_definition_versions"
    __table_args__ = (
        UniqueConstraint(
            "definition_id", "semantic_version", name="uq_oikb_definition_semantic_version"
        ),
        UniqueConstraint("definition_id", "fingerprint", name="uq_oikb_definition_fingerprint"),
        CheckConstraint(
            "lifecycle_status IN "
            "('draft','in_review','validated','approved','active','deprecated','retired','rejected')",
            name="ck_oikb_version_lifecycle",
        ),
        CheckConstraint(
            "quality_level IN "
            "('experimental','provisional','validated','production','reference_grade')",
            name="ck_oikb_version_quality",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_from IS NULL OR effective_to > effective_from",
            name="ck_oikb_version_effective_dates",
        ),
        Index("ix_oikb_version_definition", "definition_id"),
        Index("ix_oikb_version_status_effective", "lifecycle_status", "effective_from"),
        Index(
            "uq_oikb_one_active_version",
            "definition_id",
            unique=True,
            postgresql_where=text("lifecycle_status = 'active'"),
            sqlite_where=text("lifecycle_status = 'active'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    definition_id: Mapped[UUID] = mapped_column(
        ForeignKey("oikb_definitions.id", ondelete="CASCADE")
    )
    semantic_version: Mapped[str] = mapped_column(String(30))
    lifecycle_status: Mapped[str] = mapped_column(String(30), default="draft")
    quality_level: Mapped[str] = mapped_column(String(30), default="experimental")
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expression_schema: Mapped[dict[str, object]] = mapped_column(portable_json)
    output_type: Mapped[str] = mapped_column(String(50))
    output_unit: Mapped[str] = mapped_column(String(50))
    currency_code: Mapped[str | None] = mapped_column(String(3), nullable=True)
    rounding_policy: Mapped[dict[str, object]] = mapped_column(portable_json)
    null_policy: Mapped[str] = mapped_column(String(50))
    zero_denominator_policy: Mapped[str] = mapped_column(String(50))
    trust_requirement: Mapped[dict[str, object]] = mapped_column(portable_json)
    readiness_requirement: Mapped[dict[str, object]] = mapped_column(portable_json)
    fingerprint: Mapped[str] = mapped_column(String(64))
    validation_satisfied: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    activated_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    definition: Mapped[OIKBDefinition] = relationship(back_populates="versions")
    input_requirements: Mapped[list[OIKBInputRequirement]] = relationship(
        cascade="all, delete-orphan"
    )
    evidence_requirements: Mapped[list[OIKBEvidenceRequirement]] = relationship(
        cascade="all, delete-orphan"
    )
    parameters: Mapped[list[OIKBParameter]] = relationship(cascade="all, delete-orphan")


class OIKBParameter(Base):
    __tablename__ = "oikb_parameters"
    __table_args__ = (
        UniqueConstraint("definition_version_id", "parameter_code", name="uq_oikb_parameter_code"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    definition_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("oikb_definition_versions.id", ondelete="CASCADE"), index=True
    )
    parameter_code: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    data_type: Mapped[str] = mapped_column(String(30))
    default_value: Mapped[object | None] = mapped_column(portable_json, nullable=True)
    minimum_value: Mapped[str | None] = mapped_column(String(100), nullable=True)
    maximum_value: Mapped[str | None] = mapped_column(String(100), nullable=True)
    allowed_values: Mapped[list[object] | None] = mapped_column(portable_json, nullable=True)
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class OIKBInputRequirement(Base):
    __tablename__ = "oikb_input_requirements"
    __table_args__ = (
        UniqueConstraint(
            "definition_version_id", "input_code", name="uq_oikb_input_requirement_code"
        ),
        CheckConstraint(
            "allowed_null_percentage >= 0 AND allowed_null_percentage <= 100",
            name="ck_oikb_input_null_percentage",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    definition_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("oikb_definition_versions.id", ondelete="CASCADE"), index=True
    )
    input_code: Mapped[str] = mapped_column(String(100))
    canonical_entity: Mapped[str] = mapped_column(String(100))
    canonical_field: Mapped[str] = mapped_column(String(100))
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    expected_type: Mapped[str] = mapped_column(String(30))
    expected_unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    currency_code: Mapped[str | None] = mapped_column(String(3), nullable=True)
    minimum_record_count: Mapped[int] = mapped_column(Integer, default=0)
    allowed_null_percentage: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class OIKBEvidenceRequirement(Base):
    __tablename__ = "oikb_evidence_requirements"
    __table_args__ = (
        UniqueConstraint(
            "definition_version_id", "requirement_code", name="uq_oikb_evidence_requirement"
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    definition_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("oikb_definition_versions.id", ondelete="CASCADE"), index=True
    )
    evidence_type: Mapped[str] = mapped_column(String(50))
    requirement_code: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    minimum_count: Mapped[int] = mapped_column(Integer, default=1)
    retention_class: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class OIKBSource(Base):
    __tablename__ = "oikb_sources"
    __table_args__ = (Index("ix_oikb_source_authority", "authority_level"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    source_type: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(250))
    publisher: Mapped[str] = mapped_column(String(200))
    citation: Mapped[str] = mapped_column(Text)
    source_uri: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    publication_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    authority_level: Mapped[str] = mapped_column(String(50))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class OIKBDefinitionSource(Base):
    __tablename__ = "oikb_definition_sources"
    __table_args__ = (
        UniqueConstraint("definition_version_id", "source_id", name="uq_oikb_definition_source"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    definition_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("oikb_definition_versions.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("oikb_sources.id", ondelete="RESTRICT"), index=True
    )
    relationship_type: Mapped[str] = mapped_column(String(50))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class OIKBValidationCase(Base):
    __tablename__ = "oikb_validation_cases"
    __table_args__ = (
        UniqueConstraint("definition_version_id", "case_code", name="uq_oikb_validation_case"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    definition_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("oikb_definition_versions.id", ondelete="CASCADE"), index=True
    )
    case_code: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    input_payload: Mapped[dict[str, object]] = mapped_column(portable_json)
    expected_output: Mapped[object] = mapped_column(portable_json)
    tolerance: Mapped[str | None] = mapped_column(String(100), nullable=True)
    expected_status: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class OIKBValidationResult(Base):
    __tablename__ = "oikb_validation_results"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    definition_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("oikb_definition_versions.id", ondelete="CASCADE"), index=True
    )
    validation_case_id: Mapped[UUID] = mapped_column(
        ForeignKey("oikb_validation_cases.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(30))
    actual_output: Mapped[object | None] = mapped_column(portable_json, nullable=True)
    variance: Mapped[str | None] = mapped_column(String(100), nullable=True)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    executed_by: Mapped[UUID] = mapped_column(Uuid)
    engine_version: Mapped[str] = mapped_column(String(50))
    definition_fingerprint: Mapped[str] = mapped_column(String(64))
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class OIKBApproval(Base):
    __tablename__ = "oikb_approvals"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    definition_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("oikb_definition_versions.id", ondelete="CASCADE"), index=True
    )
    approval_role: Mapped[str] = mapped_column(String(50))
    approver_id: Mapped[UUID] = mapped_column(Uuid)
    decision: Mapped[str] = mapped_column(String(30))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class OIKBChangeLog(Base):
    __tablename__ = "oikb_change_log"
    __table_args__ = (Index("ix_oikb_change_definition_time", "definition_id", "occurred_at"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    definition_id: Mapped[UUID] = mapped_column(
        ForeignKey("oikb_definitions.id", ondelete="CASCADE")
    )
    definition_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("oikb_definition_versions.id", ondelete="CASCADE"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(50))
    previous_state: Mapped[str | None] = mapped_column(String(30), nullable=True)
    new_state: Mapped[str | None] = mapped_column(String(30), nullable=True)
    actor_id: Mapped[UUID] = mapped_column(Uuid)
    reason: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class OIKBRelationship(Base):
    __tablename__ = "oikb_relationships"
    __table_args__ = (
        UniqueConstraint(
            "source_definition_id",
            "target_definition_id",
            "relationship_type",
            name="uq_oikb_relationship",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    source_definition_id: Mapped[UUID] = mapped_column(
        ForeignKey("oikb_definitions.id", ondelete="CASCADE")
    )
    target_definition_id: Mapped[UUID] = mapped_column(
        ForeignKey("oikb_definitions.id", ondelete="CASCADE")
    )
    relationship_type: Mapped[str] = mapped_column(String(50))
    relationship_metadata: Mapped[dict[str, object]] = mapped_column(
        "metadata_json", portable_json, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
