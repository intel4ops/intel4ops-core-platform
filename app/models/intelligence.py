from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
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
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.entities import utc_now
from app.models.source_system import enum_values, portable_json


class IntelligenceExecutionType(StrEnum):
    CALCULATION = "calculation"
    RULE = "rule"


class IntelligenceExecutionStatus(StrEnum):
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"


class IntelligenceExecution(Base):
    __tablename__ = "intelligence_executions"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_intelligence_executions_organization_idempotency",
        ),
        CheckConstraint(
            f"execution_type IN ({enum_values(IntelligenceExecutionType)})",
            name="ck_intelligence_execution_type",
        ),
        CheckConstraint(
            f"status IN ({enum_values(IntelligenceExecutionStatus)})",
            name="ck_intelligence_execution_status",
        ),
        CheckConstraint(
            "checked_record_count >= 0 AND excluded_record_count >= 0 AND "
            "affected_record_count >= 0 AND affected_record_count <= checked_record_count",
            name="ck_intelligence_execution_counts",
        ),
        Index("ix_intelligence_executions_organization_id", "organization_id"),
        Index("ix_intelligence_executions_dataset_id", "dataset_id"),
        Index("ix_intelligence_executions_trust_assessment_id", "trust_assessment_id"),
        Index("ix_intelligence_executions_definition", "definition_code", "definition_version"),
        Index("ix_intelligence_executions_status", "status"),
        Index("ix_intelligence_executions_created_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    dataset_id: Mapped[UUID] = mapped_column(ForeignKey("datasets.id", ondelete="RESTRICT"))
    dataset_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="RESTRICT"), nullable=True
    )
    trust_assessment_id: Mapped[UUID] = mapped_column(
        ForeignKey("trust_assessments.id", ondelete="RESTRICT")
    )
    readiness_decision_id: Mapped[UUID] = mapped_column(
        ForeignKey("analytical_readiness_decisions.id", ondelete="RESTRICT")
    )
    execution_type: Mapped[str] = mapped_column(String(30))
    definition_code: Mapped[str] = mapped_column(String(100))
    definition_version: Mapped[str] = mapped_column(String(30))
    definition_fingerprint: Mapped[str] = mapped_column(String(64))
    input_fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30))
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    parameters_json: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    result_value: Mapped[Decimal | None] = mapped_column(Numeric(38, 12), nullable=True)
    comparison_value: Mapped[Decimal | None] = mapped_column(Numeric(38, 12), nullable=True)
    threshold_value: Mapped[Decimal | None] = mapped_column(Numeric(38, 12), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    breached: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    checked_record_count: Mapped[int] = mapped_column(Integer, default=0)
    excluded_record_count: Mapped[int] = mapped_column(Integer, default=0)
    affected_record_count: Mapped[int] = mapped_column(Integer, default=0)
    exposure_value: Mapped[Decimal | None] = mapped_column(Numeric(38, 12), nullable=True)
    exposure_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    blocking_rule_codes: Mapped[list[str]] = mapped_column(portable_json, default=list)
    warning_rule_codes: Mapped[list[str]] = mapped_column(portable_json, default=list)
    warnings: Mapped[list[str]] = mapped_column(portable_json, default=list)
    limitations: Mapped[list[str]] = mapped_column(portable_json, default=list)
    non_execution_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_period_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    input_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    evaluation_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    evidence: Mapped[list["IntelligenceExecutionEvidence"]] = relationship(
        back_populates="execution", cascade="all, delete-orphan", passive_deletes=True
    )


class IntelligenceExecutionEvidence(Base):
    __tablename__ = "intelligence_execution_evidence"
    __table_args__ = (
        CheckConstraint(
            "contributing_record_count >= 0 AND excluded_record_count >= 0",
            name="ck_intelligence_evidence_counts",
        ),
        CheckConstraint(
            "raw_record_reference_id IS NOT NULL OR lineage_node_id IS NOT NULL OR "
            "canonical_record_identifier IS NOT NULL OR aggregate_reference IS NOT NULL",
            name="ck_intelligence_evidence_reference",
        ),
        Index("ix_intelligence_evidence_organization_id", "organization_id"),
        Index("ix_intelligence_evidence_execution_id", "execution_id"),
        Index("ix_intelligence_evidence_raw_record_id", "raw_record_reference_id"),
        Index("ix_intelligence_evidence_lineage_node_id", "lineage_node_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    execution_id: Mapped[UUID] = mapped_column(
        ForeignKey("intelligence_executions.id", ondelete="CASCADE")
    )
    raw_record_reference_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("raw_record_references.id", ondelete="RESTRICT"), nullable=True
    )
    lineage_node_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("lineage_nodes.id", ondelete="RESTRICT"), nullable=True
    )
    canonical_record_identifier: Mapped[str | None] = mapped_column(String(255), nullable=True)
    aggregate_reference: Mapped[dict[str, object] | None] = mapped_column(
        portable_json, nullable=True
    )
    contributing_record_count: Mapped[int] = mapped_column(Integer, default=0)
    excluded_record_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    execution: Mapped[IntelligenceExecution] = relationship(back_populates="evidence")
