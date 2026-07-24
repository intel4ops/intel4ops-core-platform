from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
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
from app.models.entities import Organization, utc_now
from app.models.source_system import DataClassification, SourceSystem, enum_values, portable_json


class IngestionMethod(StrEnum):
    API = "api"
    DATABASE_EXTRACT = "database_extract"
    FILE_UPLOAD = "file_upload"
    FILE_DROP = "file_drop"
    SFTP = "sftp"
    WEBHOOK = "webhook"
    MESSAGE_QUEUE = "message_queue"
    EMAIL_INGESTION = "email_ingestion"
    MANUAL = "manual"
    DEVICE_STREAM = "device_stream"
    SIMULATED = "simulated"
    CUSTOM = "custom"


class TriggerType(StrEnum):
    MANUAL = "manual"
    SCHEDULED = "scheduled"
    EVENT = "event"
    WEBHOOK = "webhook"
    RETRY = "retry"
    BACKFILL = "backfill"
    SIMULATION = "simulation"
    SYSTEM = "system"


class IngestionBatchStatus(StrEnum):
    RECEIVED = "received"
    QUEUED = "queued"
    VALIDATING = "validating"
    PROCESSING = "processing"
    PARTIALLY_COMPLETED = "partially_completed"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    QUARANTINED = "quarantined"


class DatasetType(StrEnum):
    TRANSACTIONAL = "transactional"
    MASTER_DATA = "master_data"
    REFERENCE_DATA = "reference_data"
    EVENT_STREAM = "event_stream"
    SNAPSHOT = "snapshot"
    TIME_SERIES = "time_series"
    DOCUMENT = "document"
    GEOSPATIAL = "geospatial"
    UNSTRUCTURED = "unstructured"
    SEMI_STRUCTURED = "semi_structured"
    CUSTOM = "custom"


class DatasetStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    DEPRECATED = "deprecated"
    DECOMMISSIONED = "decommissioned"


class DatasetVersionStatus(StrEnum):
    RECEIVED = "received"
    VALIDATING = "validating"
    ACCEPTED = "accepted"
    PARTIALLY_ACCEPTED = "partially_accepted"
    REJECTED = "rejected"
    QUARANTINED = "quarantined"
    PROCESSED = "processed"
    FAILED = "failed"


class SchemaStatus(StrEnum):
    UNKNOWN = "unknown"
    DISCOVERED = "discovered"
    STABLE = "stable"
    CHANGED = "changed"
    INCOMPATIBLE = "incompatible"
    APPROVED = "approved"


class DatasetDomain(StrEnum):
    SALES = "sales"
    INVOICES = "invoices"
    PAYMENTS = "payments"
    CUSTOMERS = "customers"
    SUPPLIERS = "suppliers"
    PROCUREMENT = "procurement"
    INVENTORY = "inventory"
    GENERAL_LEDGER = "general_ledger"
    CASH = "cash"
    MAINTENANCE = "maintenance"
    ASSETS = "assets"
    WORK_ORDERS = "work_orders"
    OPERATIONS = "operations"
    PRODUCTION = "production"
    FUEL = "fuel"
    GPS = "gps"
    DISPATCH = "dispatch"
    SCHEDULING = "scheduling"
    WORKFORCE = "workforce"
    SAFETY = "safety"
    QUALITY = "quality"
    DOCUMENTS = "documents"
    CUSTOM = "custom"


class IngestionBatch(Base):
    __tablename__ = "ingestion_batches"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "batch_number", name="uq_ingestion_batches_organization_batch"
        ),
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_ingestion_batches_organization_idempotency",
        ),
        CheckConstraint(
            f"ingestion_method IN ({enum_values(IngestionMethod)})",
            name="ck_ingestion_batches_method",
        ),
        CheckConstraint(
            f"status IN ({enum_values(IngestionBatchStatus)})",
            name="ck_ingestion_batches_status",
        ),
        CheckConstraint(
            f"trigger_type IN ({enum_values(TriggerType)})",
            name="ck_ingestion_batches_trigger",
        ),
        CheckConstraint(
            "expected_dataset_count IS NULL OR expected_dataset_count >= 0",
            name="ck_ingestion_batches_expected_datasets",
        ),
        CheckConstraint(
            "actual_dataset_count >= 0 AND actual_record_count >= 0 AND "
            "accepted_record_count >= 0 AND rejected_record_count >= 0 AND "
            "warning_count >= 0 AND error_count >= 0",
            name="ck_ingestion_batches_counts_nonnegative",
        ),
        CheckConstraint(
            "expected_record_count IS NULL OR expected_record_count >= 0",
            name="ck_ingestion_batches_expected_records",
        ),
        CheckConstraint(
            "accepted_record_count + rejected_record_count <= actual_record_count",
            name="ck_ingestion_batches_counts_reconciled",
        ),
        Index("ix_ingestion_batches_organization_id", "organization_id"),
        Index("ix_ingestion_batches_source_system_id", "source_system_id"),
        Index("ix_ingestion_batches_status", "status"),
        Index("ix_ingestion_batches_ingestion_method", "ingestion_method"),
        Index("ix_ingestion_batches_trigger_type", "trigger_type"),
        Index("ix_ingestion_batches_received_at", "received_at"),
        Index("ix_ingestion_batches_correlation_id", "correlation_id"),
        Index("ix_ingestion_batches_external_batch_id", "external_batch_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    source_system_id: Mapped[UUID] = mapped_column(
        ForeignKey("source_systems.id", ondelete="RESTRICT")
    )
    batch_number: Mapped[str] = mapped_column(String(120))
    ingestion_method: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(30), default=IngestionBatchStatus.RECEIVED.value)
    trigger_type: Mapped[str] = mapped_column(String(30))
    submitted_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    source_period_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expected_dataset_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_dataset_count: Mapped[int] = mapped_column(Integer, default=0)
    expected_record_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_record_count: Mapped[int] = mapped_column(Integer, default=0)
    accepted_record_count: Mapped[int] = mapped_column(Integer, default=0)
    rejected_record_count: Mapped[int] = mapped_column(Integer, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    checksum: Mapped[str | None] = mapped_column(String(255), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_batch_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    storage_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    manifest_metadata: Mapped[dict[str, object] | None] = mapped_column(
        portable_json, nullable=True
    )
    failure_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    failure_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    organization: Mapped[Organization] = relationship()
    source_system: Mapped[SourceSystem] = relationship()
    dataset_versions: Mapped[list[DatasetVersion]] = relationship(back_populates="ingestion_batch")


class Dataset(Base):
    __tablename__ = "datasets"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_datasets_organization_code"),
        CheckConstraint(f"dataset_type IN ({enum_values(DatasetType)})", name="ck_datasets_type"),
        CheckConstraint(
            f"sensitivity IN ({enum_values(DataClassification)})",
            name="ck_datasets_sensitivity",
        ),
        CheckConstraint(f"status IN ({enum_values(DatasetStatus)})", name="ck_datasets_status"),
        CheckConstraint(
            f"schema_status IN ({enum_values(SchemaStatus)})",
            name="ck_datasets_schema_status",
        ),
        CheckConstraint(
            "retention_days IS NULL OR retention_days > 0",
            name="ck_datasets_retention_days",
        ),
        Index("ix_datasets_organization_id", "organization_id"),
        Index("ix_datasets_source_system_id", "source_system_id"),
        Index("ix_datasets_domain", "domain"),
        Index("ix_datasets_dataset_type", "dataset_type"),
        Index("ix_datasets_status", "status"),
        Index("ix_datasets_sensitivity", "sensitivity"),
        Index("ix_datasets_schema_status", "schema_status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    source_system_id: Mapped[UUID] = mapped_column(
        ForeignKey("source_systems.id", ondelete="RESTRICT")
    )
    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    domain: Mapped[str] = mapped_column(String(100))
    dataset_type: Mapped[str] = mapped_column(String(40))
    sensitivity: Mapped[str] = mapped_column(String(30), default=DataClassification.INTERNAL.value)
    status: Mapped[str] = mapped_column(String(30), default=DatasetStatus.DRAFT.value)
    schema_status: Mapped[str] = mapped_column(String(30), default=SchemaStatus.UNKNOWN.value)
    primary_time_field: Mapped[str | None] = mapped_column(String(150), nullable=True)
    primary_business_key: Mapped[str | None] = mapped_column(String(150), nullable=True)
    source_object_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_schema_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_table_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_pattern: Mapped[str | None] = mapped_column(String(255), nullable=True)
    default_timezone: Mapped[str | None] = mapped_column(String(100), nullable=True)
    default_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    retention_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict[str, object] | None] = mapped_column(portable_json, nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    updated_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    organization: Mapped[Organization] = relationship()
    source_system: Mapped[SourceSystem] = relationship()
    versions: Mapped[list[DatasetVersion]] = relationship(back_populates="dataset")


class DatasetVersion(Base):
    __tablename__ = "dataset_versions"
    __table_args__ = (
        UniqueConstraint(
            "dataset_id", "version_number", name="uq_dataset_versions_dataset_version"
        ),
        UniqueConstraint(
            "ingestion_batch_id",
            "dataset_id",
            name="uq_dataset_versions_batch_dataset",
        ),
        CheckConstraint("version_number > 0", name="ck_dataset_versions_version_positive"),
        CheckConstraint(
            f"status IN ({enum_values(DatasetVersionStatus)})",
            name="ck_dataset_versions_status",
        ),
        CheckConstraint(
            "record_count >= 0 AND accepted_record_count >= 0 AND rejected_record_count >= 0",
            name="ck_dataset_versions_counts_nonnegative",
        ),
        CheckConstraint(
            "accepted_record_count + rejected_record_count <= record_count",
            name="ck_dataset_versions_counts_reconciled",
        ),
        CheckConstraint(
            "source_file_size_bytes IS NULL OR source_file_size_bytes >= 0",
            name="ck_dataset_versions_file_size",
        ),
        CheckConstraint(
            "column_count IS NULL OR column_count >= 0",
            name="ck_dataset_versions_column_count",
        ),
        Index("ix_dataset_versions_organization_id", "organization_id"),
        Index("ix_dataset_versions_dataset_id", "dataset_id"),
        Index("ix_dataset_versions_ingestion_batch_id", "ingestion_batch_id"),
        Index("ix_dataset_versions_status", "status"),
        Index("ix_dataset_versions_received_at", "received_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    dataset_id: Mapped[UUID] = mapped_column(ForeignKey("datasets.id", ondelete="RESTRICT"))
    ingestion_batch_id: Mapped[UUID] = mapped_column(
        ForeignKey("ingestion_batches.id", ondelete="RESTRICT")
    )
    version_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default=DatasetVersionStatus.RECEIVED.value)
    source_file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_file_extension: Mapped[str | None] = mapped_column(String(30), nullable=True)
    source_file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_file_checksum: Mapped[str | None] = mapped_column(String(255), nullable=True)
    media_type: Mapped[str | None] = mapped_column(String(150), nullable=True)
    encoding: Mapped[str | None] = mapped_column(String(50), nullable=True)
    delimiter: Mapped[str | None] = mapped_column(String(10), nullable=True)
    sheet_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    accepted_record_count: Mapped[int] = mapped_column(Integer, default=0)
    rejected_record_count: Mapped[int] = mapped_column(Integer, default=0)
    column_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    storage_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    raw_schema_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_period_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    schema_fingerprint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[dict[str, object] | None] = mapped_column(portable_json, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    dataset: Mapped[Dataset] = relationship(back_populates="versions")
    ingestion_batch: Mapped[IngestionBatch] = relationship(back_populates="dataset_versions")
