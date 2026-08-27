from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.entities import utc_now
from app.models.source_system import enum_values, portable_json

# ---------------------------------------------------------------------------
# Enums. Status-style fields (small, genuinely closed sets) get DB CHECK
# constraints, matching this repo's convention. Domain/entity-type values are
# deliberately NOT enums here -- they are validated against the extensible
# app-level registry in app/domain_registry.py instead, so adding a new
# industry's domain/entity vocabulary is a data change, never a migration.
# ---------------------------------------------------------------------------


class AnalysisCaseMode(StrEnum):
    SINGLE = "single"
    ORCHESTRATED = "orchestrated"


class AnalysisCaseStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    REVIEW_REQUIRED = "review_required"
    PARTIAL = "partial"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AnalysisCaseRunStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    INTERRUPTED = "interrupted"
    REVIEW_REQUIRED = "review_required"
    PARTIAL = "partial"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ArtifactParserStatus(StrEnum):
    PENDING = "pending"
    PARSED = "parsed"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"


class ArtifactExtractionStatus(StrEnum):
    PENDING = "pending"
    EXTRACTED = "extracted"
    PARTIAL = "partial"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


class DetectionStatus(StrEnum):
    CONFIRMED = "confirmed"
    NEEDS_REVIEW = "needs_review"
    UNKNOWN = "unknown"


class MappingStatus(StrEnum):
    AUTO_MAPPED = "auto_mapped"
    NEEDS_REVIEW = "needs_review"
    MISSING_REQUIRED_FIELD = "missing_required_field"
    IGNORED = "ignored"


class EntityLinkStatus(StrEnum):
    MATCHED = "matched"
    UNRESOLVED = "unresolved"
    CONFLICT = "conflict"


class StageEventStatus(StrEnum):
    STARTED = "started"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


class AnalysisCaseActionStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class RecoveryStatus(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    AWAITING_VERIFICATION = "awaiting_verification"
    VERIFIED = "verified"
    NOT_VERIFIED = "not_verified"


class CurrencyStatus(StrEnum):
    CONFIRMED = "confirmed"
    INFERRED = "inferred"
    UNRESOLVED = "unresolved"


# Canonical base entity types (Section: canonical entities). Deliberately a
# plain frozenset used for app-level validation, not a DB CHECK constraint --
# an industry pack may need entity_subtype extensions without a migration.
BASE_CANONICAL_ENTITY_TYPES = frozenset(
    {
        "organization",
        "asset",
        "location",
        "operational_event",
        "work_order",
        "customer",
        "product_service",
        "employee_crew",
        "material",
        "transaction",
        "time_period",
    }
)


class AnalysisCase(Base):
    """Durable business-analysis container. Carries no execution identity of
    its own -- see AnalysisCaseRun for that. A case may be executed any
    number of times; run history is never overwritten (required for
    Validation Lab regression comparison between runs)."""

    __tablename__ = "analysis_cases"
    __table_args__ = (
        UniqueConstraint("case_code"),
        UniqueConstraint("organization_id", "idempotency_key"),
        UniqueConstraint("organization_id", "id"),
        CheckConstraint(f"mode IN ({enum_values(AnalysisCaseMode)})", name="ck_analysis_case_mode"),
        CheckConstraint(
            f"status IN ({enum_values(AnalysisCaseStatus)})", name="ck_analysis_case_status"
        ),
        Index("ix_analysis_cases_org_status", "organization_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    case_code: Mapped[str] = mapped_column(String(40), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=AnalysisCaseStatus.CREATED
    )

    # Optional, advisory-only industry context. Never required, never gates
    # what can run -- actual uploaded/mapped data remains authoritative. Used
    # only to help the Intelligence Pack Registry narrow candidates faster.
    industry_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    business_model: Mapped[str | None] = mapped_column(String(60), nullable=True)
    operating_context: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Weakest tier of the currency-resolution hierarchy: an inferred
    # candidate only, never overriding a record/dataset-level currency.
    case_currency_hint: Mapped[str | None] = mapped_column(String(3), nullable=True)

    created_by_user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    # P3.xxC.1E: soft-archive only, mirroring Finding.archived_at -- never a
    # delete. Archiving hides a case from the default list view; every
    # artifact, dataset, run, finding, action, and recovery record remains
    # fully intact and directly retrievable by id, preserving the audit
    # trail this feature is built around.
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)

    runs: Mapped[list[AnalysisCaseRun]] = relationship(
        back_populates="analysis_case", cascade="all, delete-orphan"
    )
    artifacts: Mapped[list[SourceArtifact]] = relationship(
        back_populates="analysis_case", cascade="all, delete-orphan"
    )
    datasets: Mapped[list[AnalysisCaseDataset]] = relationship(
        back_populates="analysis_case", cascade="all, delete-orphan"
    )


class AnalysisCaseRun(Base):
    """One execution of an AnalysisCase. Carries the lease/heartbeat shape
    mirrored from MappingRun so a future real external worker can adopt it
    without a schema change -- execution itself uses FastAPI BackgroundTasks
    for this phase. A partial unique index (below) prevents two concurrently
    non-terminal runs on the same case."""

    __tablename__ = "analysis_case_runs"
    __table_args__ = (
        UniqueConstraint("analysis_case_id", "run_number"),
        CheckConstraint(
            f"status IN ({enum_values(AnalysisCaseRunStatus)})", name="ck_analysis_case_run_status"
        ),
        Index("ix_analysis_case_runs_org_case", "organization_id", "analysis_case_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    analysis_case_id: Mapped[UUID] = mapped_column(
        ForeignKey("analysis_cases.id", ondelete="CASCADE"), nullable=False
    )
    run_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=AnalysisCaseRunStatus.CREATED
    )
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    execution_claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    execution_lease_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Version of the orchestration engine that produced this run -- part of
    # the Validation Lab provenance chain alongside pack/rule code+version.
    orchestration_version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    analysis_case: Mapped[AnalysisCase] = relationship(back_populates="runs")


class SourceArtifact(Base):
    """The universal upload primitive -- every uploaded file becomes a row
    here, with bytes persisted via the storage layer, regardless of whether
    a parser exists for it. parent_artifact_id supports compound artifacts
    (a multi-sheet workbook's sheets, an email's attachments)."""

    __tablename__ = "source_artifacts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "analysis_case_id"],
            ["analysis_cases.organization_id", "analysis_cases.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(
            f"parser_status IN ({enum_values(ArtifactParserStatus)})",
            name="ck_source_artifact_parser_status",
        ),
        CheckConstraint(
            f"extraction_status IN ({enum_values(ArtifactExtractionStatus)})",
            name="ck_source_artifact_extraction_status",
        ),
        Index("ix_source_artifacts_org_case", "organization_id", "analysis_case_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    analysis_case_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    parent_artifact_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("source_artifacts.id", ondelete="CASCADE"), nullable=True
    )
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(150), nullable=False)
    extension: Mapped[str] = mapped_column(String(20), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    # Generated storage key, never the client filename -- see app/storage/.
    storage_reference: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_system: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ingestion_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    parser_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ArtifactParserStatus.PENDING
    )
    parser_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    parser_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    extraction_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ArtifactExtractionStatus.PENDING
    )
    extraction_warnings: Mapped[list[str]] = mapped_column(portable_json, default=list)
    extraction_metadata: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    analysis_case: Mapped[AnalysisCase] = relationship(back_populates="artifacts")


class AnalysisCaseDataset(Base):
    """One logical, tabular dataset extracted from a SourceArtifact (e.g.
    one sheet of a workbook). Tracks the dataset's progress through
    detection/mapping/trust/intelligence independently of sibling datasets
    in the same case."""

    __tablename__ = "analysis_case_datasets"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "analysis_case_id"],
            ["analysis_cases.organization_id", "analysis_cases.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("analysis_case_id", "dataset_id"),
        CheckConstraint(
            f"detection_status IN ({enum_values(DetectionStatus)})",
            name="ck_analysis_case_dataset_detection_status",
        ),
        Index("ix_analysis_case_datasets_org_case", "organization_id", "analysis_case_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    analysis_case_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    source_artifact_id: Mapped[UUID] = mapped_column(
        ForeignKey("source_artifacts.id", ondelete="CASCADE"), nullable=False
    )
    dataset_id: Mapped[UUID] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False
    )
    dataset_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="SET NULL"), nullable=True
    )
    source_label: Mapped[str] = mapped_column(String(200), nullable=False)
    # Free-text, app-registry-validated against app/domain_registry.py --
    # deliberately not a DB CHECK constraint (industry-agnostic requirement).
    detected_domain: Mapped[str | None] = mapped_column(String(60), nullable=True)
    detection_basis: Mapped[list[str]] = mapped_column(portable_json, default=list)
    detection_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=DetectionStatus.UNKNOWN
    )
    trust_assessment_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    trust_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    mapping_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    intelligence_readiness_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    analysis_case: Mapped[AnalysisCase] = relationship(back_populates="datasets")


class AnalysisCaseFieldMapping(Base):
    """MVP deterministic mapping bridge: one row per (dataset, source field,
    canonical field). Deliberately structured so a validated case mapping
    can be promoted into a real governed MappingTemplateVersion/FieldMapping
    later without losing lineage of which source column fed which canonical
    field."""

    __tablename__ = "analysis_case_field_mappings"
    __table_args__ = (
        UniqueConstraint("analysis_case_dataset_id", "source_field"),
        CheckConstraint(
            f"mapping_status IN ({enum_values(MappingStatus)})",
            name="ck_analysis_case_field_mapping_status",
        ),
        Index("ix_analysis_case_field_mappings_org", "organization_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    analysis_case_dataset_id: Mapped[UUID] = mapped_column(
        ForeignKey("analysis_case_datasets.id", ondelete="CASCADE"), nullable=False
    )
    source_field: Mapped[str] = mapped_column(String(200), nullable=False)
    canonical_field: Mapped[str | None] = mapped_column(String(200), nullable=True)
    mapping_status: Mapped[str] = mapped_column(String(30), nullable=False)
    mapping_basis: Mapped[str] = mapped_column(
        String(60), nullable=False, default="mvp_alias_table_v1"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AnalysisCaseEntityLink(Base):
    """Cross-dataset entity resolution result. Operates on canonical field
    values only (post-mapping) -- exact match, no fuzzy matching where an
    exact business identifier exists."""

    __tablename__ = "analysis_case_entity_links"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "analysis_case_id"],
            ["analysis_cases.organization_id", "analysis_cases.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("analysis_case_id", "entity_type", "canonical_key"),
        CheckConstraint(
            f"status IN ({enum_values(EntityLinkStatus)})",
            name="ck_analysis_case_entity_link_status",
        ),
        Index("ix_analysis_case_entity_links_org_case", "organization_id", "analysis_case_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    analysis_case_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_subtype: Mapped[str | None] = mapped_column(String(60), nullable=True)
    canonical_key: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    source_dataset_ids: Mapped[list[str]] = mapped_column(portable_json, default=list)
    detail: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AnalysisCaseEvidenceObject(Base):
    """Non-tabular extracted content (document narrative text, email
    bodies, slide notes) that Intelligence can cite as evidence without
    forcing it into a dataframe."""

    __tablename__ = "analysis_case_evidence_objects"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "analysis_case_id"],
            ["analysis_cases.organization_id", "analysis_cases.id"],
            ondelete="CASCADE",
        ),
        Index("ix_analysis_case_evidence_objects_org_case", "organization_id", "analysis_case_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    analysis_case_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    source_artifact_id: Mapped[UUID] = mapped_column(
        ForeignKey("source_artifacts.id", ondelete="CASCADE"), nullable=False
    )
    evidence_type: Mapped[str] = mapped_column(String(30), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    lineage_ref: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AnalysisCaseStageEvent(Base):
    """Append-only per-run/per-stage/per-artifact audit trail. Immutable
    once written, mirroring AccessAuditEvent's before_update/before_delete
    guards."""

    __tablename__ = "analysis_case_stage_events"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({enum_values(StageEventStatus)})",
            name="ck_analysis_case_stage_event_status",
        ),
        Index("ix_analysis_case_stage_events_org_run", "organization_id", "run_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    analysis_case_id: Mapped[UUID] = mapped_column(
        ForeignKey("analysis_cases.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("analysis_case_runs.id", ondelete="CASCADE"), nullable=False
    )
    stage: Mapped[str] = mapped_column(String(40), nullable=False)
    source_artifact_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    detail: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AnalysisCaseFinding(Base):
    """Join table: which findings a given run of a given case produced.
    Findings are attributable to the specific run, never overwritten by a
    later run."""

    __tablename__ = "analysis_case_findings"
    __table_args__ = (
        UniqueConstraint("run_id", "finding_id"),
        Index("ix_analysis_case_findings_org_case", "organization_id", "analysis_case_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    analysis_case_id: Mapped[UUID] = mapped_column(
        ForeignKey("analysis_cases.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("analysis_case_runs.id", ondelete="CASCADE"), nullable=False
    )
    finding_id: Mapped[UUID] = mapped_column(
        ForeignKey("findings.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class FindingSourceDataset(Base):
    """Generic (not case-specific) join letting any finding reference
    multiple contributing datasets, without touching Finding.dataset_id's
    existing single-FK semantics."""

    __tablename__ = "finding_source_datasets"
    __table_args__ = (
        UniqueConstraint("finding_id", "dataset_id"),
        Index("ix_finding_source_datasets_org", "organization_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    finding_id: Mapped[UUID] = mapped_column(
        ForeignKey("findings.id", ondelete="CASCADE"), nullable=False
    )
    dataset_id: Mapped[UUID] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False
    )
    dataset_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AnalysisCaseAction(Base):
    """Lightweight, case-scoped action -- NOT the full governed
    OperationalAction/RecoveryLedger pipeline (too heavy for this MVP; see
    the documented migration path in the plan). Links to findings via a
    join table (AnalysisCaseActionFinding), never a single FK, so grouping
    multiple related findings into one intervention later needs no schema
    change."""

    __tablename__ = "analysis_case_actions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "analysis_case_id"],
            ["analysis_cases.organization_id", "analysis_cases.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(
            f"status IN ({enum_values(AnalysisCaseActionStatus)})",
            name="ck_analysis_case_action_status",
        ),
        Index("ix_analysis_case_actions_org_case", "organization_id", "analysis_case_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    analysis_case_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner: Mapped[str | None] = mapped_column(String(200), nullable=True)
    priority: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=AnalysisCaseActionStatus.OPEN
    )
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class AnalysisCaseActionFinding(Base):
    """N:M join between actions and findings -- deliberately not a single
    FK on AnalysisCaseAction, so future finding-clustering (many findings
    -> one intervention) needs no schema change."""

    __tablename__ = "analysis_case_action_findings"
    __table_args__ = (
        UniqueConstraint("action_id", "finding_id"),
        Index("ix_analysis_case_action_findings_org", "organization_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    action_id: Mapped[UUID] = mapped_column(
        ForeignKey("analysis_case_actions.id", ondelete="CASCADE"), nullable=False
    )
    finding_id: Mapped[UUID] = mapped_column(
        ForeignKey("findings.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AnalysisCaseRecoveryRecord(Base):
    """Minimum closed-loop recovery tracking. verified_value may only be
    set when recovery_status == verified AND evidence_json is non-empty --
    enforced in the service layer, never merely because an action closed.
    Documented future migration path: baseline/observed/verified ->
    RecoveryValueMeasurement.baseline_amount/actual_amount/realized_value;
    recovery_status=verified + evidence_json -> RecoveryFinanceVerification.
    """

    __tablename__ = "analysis_case_recovery_records"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "analysis_case_id"],
            ["analysis_cases.organization_id", "analysis_cases.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(
            f"recovery_status IN ({enum_values(RecoveryStatus)})",
            name="ck_analysis_case_recovery_status",
        ),
        Index("ix_analysis_case_recovery_records_org_case", "organization_id", "analysis_case_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    analysis_case_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    action_id: Mapped[UUID] = mapped_column(
        ForeignKey("analysis_case_actions.id", ondelete="CASCADE"), nullable=False
    )
    finding_id: Mapped[UUID] = mapped_column(
        ForeignKey("findings.id", ondelete="CASCADE"), nullable=False
    )
    baseline_condition: Mapped[str | None] = mapped_column(Text, nullable=True)
    intervention_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    recovery_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=RecoveryStatus.NOT_STARTED
    )
    observed_post_condition: Mapped[dict[str, object] | None] = mapped_column(
        portable_json, nullable=True
    )
    observed_value: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    estimated_value: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    verified_value: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    # {observed: {currency, currency_status, currency_basis}, estimated: {...}, verified: {...}}
    currency_detail: Mapped[dict[str, object] | None] = mapped_column(portable_json, nullable=True)
    evidence_json: Mapped[dict[str, object] | None] = mapped_column(portable_json, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


def _guard_immutable_stage_event(_mapper: object, _connection: object, _target: object) -> None:
    raise ValueError("analysis case stage events are immutable")


event.listen(AnalysisCaseStageEvent, "before_update", _guard_immutable_stage_event)
event.listen(AnalysisCaseStageEvent, "before_delete", _guard_immutable_stage_event)
