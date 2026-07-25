from datetime import datetime
from decimal import Decimal
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
    event,
    inspect,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.entities import portable_json, utc_now


class FindingEvidenceBundle(Base):
    __tablename__ = "finding_evidence_bundles"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'complete', 'incomplete', 'invalid', 'superseded')",
            name="ck_finding_evidence_bundle_status",
        ),
        CheckConstraint(
            "completeness_status IN ('complete', 'incomplete', 'invalid')",
            name="ck_finding_evidence_bundle_completeness",
        ),
        UniqueConstraint(
            "finding_id",
            "bundle_version",
            name="uq_finding_evidence_bundle_version",
        ),
        Index("ix_finding_evidence_bundles_organization_id", "organization_id"),
        Index("ix_finding_evidence_bundles_finding_id", "finding_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    finding_id: Mapped[UUID] = mapped_column(ForeignKey("findings.id", ondelete="RESTRICT"))
    bundle_version: Mapped[int] = mapped_column(Integer, default=1)
    evidence_policy_code: Mapped[str] = mapped_column(String(100))
    evidence_policy_version: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30))
    completeness_status: Mapped[str] = mapped_column(String(30))
    content_hash: Mapped[str] = mapped_column(String(64))
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FindingEvidenceItem(Base):
    __tablename__ = "finding_evidence_items"
    __table_args__ = (
        CheckConstraint(
            "sequence_number > 0",
            name="ck_finding_evidence_item_sequence",
        ),
        CheckConstraint(
            "reference_id IS NOT NULL OR reference_uri IS NOT NULL OR "
            "canonical_record_reference IS NOT NULL",
            name="ck_finding_evidence_item_reference",
        ),
        UniqueConstraint(
            "evidence_bundle_id",
            "sequence_number",
            name="uq_finding_evidence_item_sequence",
        ),
        Index("ix_finding_evidence_items_organization_id", "organization_id"),
        Index("ix_finding_evidence_items_bundle_id", "evidence_bundle_id"),
        Index("ix_finding_evidence_items_reference", "reference_type", "reference_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    evidence_bundle_id: Mapped[UUID] = mapped_column(
        ForeignKey("finding_evidence_bundles.id", ondelete="RESTRICT")
    )
    evidence_type: Mapped[str] = mapped_column(String(40))
    reference_type: Mapped[str] = mapped_column(String(50))
    reference_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reference_uri: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reference_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    label: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_system_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("source_systems.id", ondelete="RESTRICT"), nullable=True
    )
    ingestion_batch_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("ingestion_batches.id", ondelete="RESTRICT"), nullable=True
    )
    dataset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("datasets.id", ondelete="RESTRICT"), nullable=True
    )
    lineage_node_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("lineage_nodes.id", ondelete="RESTRICT"), nullable=True
    )
    raw_record_reference_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("raw_record_references.id", ondelete="RESTRICT"), nullable=True
    )
    canonical_entity: Mapped[str | None] = mapped_column(String(100), nullable=True)
    canonical_record_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    field_reference: Mapped[str | None] = mapped_column(String(150), nullable=True)
    comparison_value: Mapped[Decimal | None] = mapped_column(Numeric(38, 12), nullable=True)
    comparison_unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    comparison_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    sequence_number: Mapped[int] = mapped_column(Integer)
    metadata_json: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class FindingCalculationTrace(Base):
    __tablename__ = "finding_calculation_traces"
    __table_args__ = (
        CheckConstraint(
            "sequence_number > 0",
            name="ck_finding_calculation_trace_sequence",
        ),
        UniqueConstraint(
            "finding_id",
            "sequence_number",
            name="uq_finding_calculation_trace_sequence",
        ),
        Index("ix_finding_calculation_traces_organization_id", "organization_id"),
        Index("ix_finding_calculation_traces_finding_id", "finding_id"),
        Index("ix_finding_calculation_traces_execution_id", "execution_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    finding_id: Mapped[UUID] = mapped_column(ForeignKey("findings.id", ondelete="RESTRICT"))
    execution_id: Mapped[UUID] = mapped_column(
        ForeignKey("intelligence_executions.id", ondelete="RESTRICT")
    )
    definition_code: Mapped[str] = mapped_column(String(100))
    definition_version: Mapped[str] = mapped_column(String(30))
    engine_version: Mapped[str] = mapped_column(String(30))
    operation_code: Mapped[str] = mapped_column(String(100))
    sequence_number: Mapped[int] = mapped_column(Integer)
    input_reference_summary: Mapped[dict[str, object]] = mapped_column(portable_json)
    parameter_summary: Mapped[dict[str, object]] = mapped_column(portable_json)
    output_value: Mapped[Decimal | None] = mapped_column(Numeric(38, 12), nullable=True)
    output_type: Mapped[str] = mapped_column(String(30))
    output_unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    output_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    warnings: Mapped[list[str]] = mapped_column(portable_json, default=list)
    content_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class FindingRuleTrace(Base):
    __tablename__ = "finding_rule_traces"
    __table_args__ = (
        CheckConstraint(
            "sequence_number > 0",
            name="ck_finding_rule_trace_sequence",
        ),
        UniqueConstraint(
            "finding_id",
            "sequence_number",
            name="uq_finding_rule_trace_sequence",
        ),
        Index("ix_finding_rule_traces_organization_id", "organization_id"),
        Index("ix_finding_rule_traces_finding_id", "finding_id"),
        Index("ix_finding_rule_traces_execution_id", "execution_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    finding_id: Mapped[UUID] = mapped_column(ForeignKey("findings.id", ondelete="RESTRICT"))
    execution_id: Mapped[UUID] = mapped_column(
        ForeignKey("intelligence_executions.id", ondelete="RESTRICT")
    )
    rule_code: Mapped[str] = mapped_column(String(100))
    rule_version: Mapped[str] = mapped_column(String(30))
    condition_code: Mapped[str] = mapped_column(String(100))
    sequence_number: Mapped[int] = mapped_column(Integer)
    evaluation_result: Mapped[bool] = mapped_column(Boolean)
    operand_reference_summary: Mapped[dict[str, object]] = mapped_column(portable_json)
    comparison_operator: Mapped[str] = mapped_column(String(50))
    threshold_summary: Mapped[dict[str, object]] = mapped_column(portable_json)
    warnings: Mapped[list[str]] = mapped_column(portable_json, default=list)
    content_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class FindingReview(Base):
    __tablename__ = "finding_reviews"
    __table_args__ = (
        Index("ix_finding_reviews_organization_id", "organization_id"),
        Index("ix_finding_reviews_finding_id", "finding_id"),
        Index("ix_finding_reviews_reviewed_at", "reviewed_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    finding_id: Mapped[UUID] = mapped_column(ForeignKey("findings.id", ondelete="RESTRICT"))
    review_status: Mapped[str] = mapped_column(String(30))
    decision: Mapped[str] = mapped_column(String(40))
    reviewer_user_id: Mapped[UUID] = mapped_column(Uuid)
    reviewer_role: Mapped[str] = mapped_column(String(50))
    reason_code: Mapped[str] = mapped_column(String(100))
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class FindingStatusHistory(Base):
    __tablename__ = "finding_status_history"
    __table_args__ = (
        Index("ix_finding_status_history_organization_id", "organization_id"),
        Index("ix_finding_status_history_finding_id", "finding_id"),
        Index("ix_finding_status_history_changed_at", "changed_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    finding_id: Mapped[UUID] = mapped_column(ForeignKey("findings.id", ondelete="RESTRICT"))
    previous_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    new_status: Mapped[str] = mapped_column(String(30))
    reason_code: Mapped[str] = mapped_column(String(100))
    changed_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)


def _immutable(_: object, __: object, target: object) -> None:
    raise ValueError(f"{type(target).__name__} is immutable")


def _bundle_immutable_after_finalization(_: object, __: object, target: object) -> None:
    state = inspect(target)
    assert state is not None
    finalized_history = state.attrs.finalized_at.history
    if target.finalized_at is not None and not finalized_history.added:  # type: ignore[attr-defined]
        raise ValueError("FindingEvidenceBundle is immutable after finalization")


event.listen(
    FindingEvidenceBundle,
    "before_update",
    _bundle_immutable_after_finalization,
)
event.listen(FindingEvidenceBundle, "before_delete", _immutable)
for _immutable_model in (
    FindingEvidenceItem,
    FindingCalculationTrace,
    FindingRuleTrace,
    FindingReview,
    FindingStatusHistory,
):
    event.listen(_immutable_model, "before_update", _immutable)
    event.listen(_immutable_model, "before_delete", _immutable)
