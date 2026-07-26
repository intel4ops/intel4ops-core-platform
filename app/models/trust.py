from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.entities import utc_now
from app.models.source_system import enum_values, portable_json


class TrustAssessmentStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TrustDimension(StrEnum):
    COMPLETENESS = "completeness"
    VALIDITY = "validity"
    CONSISTENCY = "consistency"
    UNIQUENESS = "uniqueness"
    TIMELINESS = "timeliness"
    LINEAGE = "lineage"
    REFERENTIAL_INTEGRITY = "referential_integrity"


class TrustRuleSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class TrustExecutionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    ERRORED = "errored"


class TrustResultStatus(StrEnum):
    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"
    SKIPPED = "skipped"
    NOT_APPLICABLE = "not_applicable"


class TrustEvidenceType(StrEnum):
    RECORD = "record"
    FIELD = "field"
    DUPLICATE = "duplicate"
    REFERENCE = "reference"
    SCHEMA = "schema"
    LINEAGE = "lineage"
    SUMMARY = "summary"


class AnalyticalLevel(StrEnum):
    ARITHMETIC = "arithmetic"
    STATISTICAL = "statistical"
    FORECASTING = "forecasting"
    RELIABILITY = "reliability"
    PREDICTIVE = "predictive"
    OPTIMIZATION = "optimization"
    ECONOMIC_RECOVERY = "economic_recovery"


class ReadinessStatus(StrEnum):
    READY = "ready"
    READY_WITH_WARNINGS = "ready_with_warnings"
    INSUFFICIENT_DATA = "insufficient_data"
    BLOCKED = "blocked"


class TrustAssessment(Base):
    __tablename__ = "trust_assessments"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({enum_values(TrustAssessmentStatus)})",
            name="ck_trust_assessment_status",
        ),
        CheckConstraint(
            "overall_score IS NULL OR (overall_score >= 0 AND overall_score <= 100)",
            name="ck_trust_assessment_overall_score",
        ),
        CheckConstraint(
            "(completeness_score IS NULL OR (completeness_score >= 0 AND "
            "completeness_score <= 100)) AND "
            "(validity_score IS NULL OR (validity_score >= 0 AND validity_score <= 100)) "
            "AND (consistency_score IS NULL OR (consistency_score >= 0 AND "
            "consistency_score <= 100)) AND "
            "(uniqueness_score IS NULL OR (uniqueness_score >= 0 AND "
            "uniqueness_score <= 100)) AND "
            "(timeliness_score IS NULL OR (timeliness_score >= 0 AND "
            "timeliness_score <= 100)) AND "
            "(lineage_score IS NULL OR (lineage_score >= 0 AND lineage_score <= 100))",
            name="ck_trust_assessment_dimension_scores",
        ),
        CheckConstraint(
            "assessed_row_count >= 0 AND passed_rule_count >= 0 AND "
            "warning_rule_count >= 0 AND failed_rule_count >= 0 AND "
            "skipped_rule_count >= 0",
            name="ck_trust_assessment_counts",
        ),
        Index("ix_trust_assessments_organization_id", "organization_id"),
        Index("ix_trust_assessments_dataset_id", "dataset_id"),
        Index("ix_trust_assessments_batch_id", "ingestion_batch_id"),
        Index("ix_trust_assessments_status", "status"),
        Index("ix_trust_assessments_created_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    dataset_id: Mapped[UUID] = mapped_column(ForeignKey("datasets.id", ondelete="RESTRICT"))
    ingestion_batch_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("ingestion_batches.id", ondelete="RESTRICT"), nullable=True
    )
    industry_pack_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default=TrustAssessmentStatus.PENDING.value)
    overall_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    completeness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    validity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    consistency_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    uniqueness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    timeliness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    lineage_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    assessed_row_count: Mapped[int] = mapped_column(Integer, default=0)
    passed_rule_count: Mapped[int] = mapped_column(Integer, default=0)
    warning_rule_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_rule_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_rule_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class TrustRuleResult(Base):
    __tablename__ = "trust_rule_results"
    __table_args__ = (
        CheckConstraint(
            f"dimension IN ({enum_values(TrustDimension)})",
            name="ck_trust_rule_dimension",
        ),
        CheckConstraint(
            f"severity IN ({enum_values(TrustRuleSeverity)})",
            name="ck_trust_rule_severity",
        ),
        CheckConstraint(
            f"execution_status IN ({enum_values(TrustExecutionStatus)})",
            name="ck_trust_rule_execution_status",
        ),
        CheckConstraint(
            f"result_status IN ({enum_values(TrustResultStatus)})",
            name="ck_trust_rule_result_status",
        ),
        CheckConstraint(
            "checked_record_count >= 0 AND affected_record_count >= 0",
            name="ck_trust_rule_counts",
        ),
        CheckConstraint(
            "affected_percentage IS NULL OR (affected_percentage >= 0 AND "
            "affected_percentage <= 100)",
            name="ck_trust_rule_affected_percentage",
        ),
        CheckConstraint(
            "score IS NULL OR (score >= 0 AND score <= 100)",
            name="ck_trust_rule_score",
        ),
        Index("ix_trust_rule_results_organization_id", "organization_id"),
        Index("ix_trust_rule_results_assessment_id", "trust_assessment_id"),
        Index("ix_trust_rule_results_rule_code", "rule_code"),
        Index("ix_trust_rule_results_result_status", "result_status"),
        Index("ix_trust_rule_results_created_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    trust_assessment_id: Mapped[UUID] = mapped_column(
        ForeignKey("trust_assessments.id", ondelete="RESTRICT")
    )
    rule_code: Mapped[str] = mapped_column(String(100))
    rule_version: Mapped[str] = mapped_column(String(30))
    rule_name: Mapped[str] = mapped_column(String(200))
    dimension: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(20))
    execution_status: Mapped[str] = mapped_column(String(20))
    result_status: Mapped[str] = mapped_column(String(30))
    checked_record_count: Mapped[int] = mapped_column(Integer, default=0)
    affected_record_count: Mapped[int] = mapped_column(Integer, default=0)
    affected_percentage: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold_definition: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    observed_value: Mapped[dict[str, object] | None] = mapped_column(portable_json, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    message: Mapped[str] = mapped_column(Text)
    remediation_guidance: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class TrustEvidence(Base):
    __tablename__ = "trust_evidence"
    __table_args__ = (
        CheckConstraint(
            f"evidence_type IN ({enum_values(TrustEvidenceType)})",
            name="ck_trust_evidence_type",
        ),
        Index("ix_trust_evidence_organization_id", "organization_id"),
        Index("ix_trust_evidence_rule_result_id", "trust_rule_result_id"),
        Index("ix_trust_evidence_dataset_id", "dataset_id"),
        Index("ix_trust_evidence_created_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    trust_rule_result_id: Mapped[UUID] = mapped_column(
        ForeignKey("trust_rule_results.id", ondelete="RESTRICT")
    )
    dataset_id: Mapped[UUID] = mapped_column(ForeignKey("datasets.id", ondelete="RESTRICT"))
    source_record_identifier: Mapped[str | None] = mapped_column(String(255), nullable=True)
    canonical_record_identifier: Mapped[str | None] = mapped_column(String(255), nullable=True)
    field_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    observed_value: Mapped[dict[str, object] | None] = mapped_column(portable_json, nullable=True)
    expected_condition: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_type: Mapped[str] = mapped_column(String(30))
    source_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AnalyticalReadinessDecision(Base):
    __tablename__ = "analytical_readiness_decisions"
    __table_args__ = (
        CheckConstraint(
            f"analytical_level IN ({enum_values(AnalyticalLevel)})",
            name="ck_readiness_level",
        ),
        CheckConstraint(
            f"readiness_status IN ({enum_values(ReadinessStatus)})",
            name="ck_readiness_status",
        ),
        Index("ix_readiness_organization_id", "organization_id"),
        Index("ix_readiness_assessment_id", "trust_assessment_id"),
        Index("ix_readiness_status", "readiness_status"),
        Index("ix_readiness_created_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    trust_assessment_id: Mapped[UUID] = mapped_column(
        ForeignKey("trust_assessments.id", ondelete="RESTRICT")
    )
    analytical_level: Mapped[str] = mapped_column(String(40))
    readiness_status: Mapped[str] = mapped_column(String(40))
    blocking_rule_codes: Mapped[list[str]] = mapped_column(portable_json, default=list)
    warning_rule_codes: Mapped[list[str]] = mapped_column(portable_json, default=list)
    explanation: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
