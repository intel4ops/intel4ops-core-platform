from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.entities import utc_now
from app.models.source_system import enum_values, portable_json


class RawObjectType(StrEnum):
    FILE = "file"
    API_PAYLOAD = "api_payload"
    DATABASE_EXTRACT = "database_extract"
    MESSAGE = "message"
    EMAIL = "email"
    EMAIL_ATTACHMENT = "email_attachment"
    DOCUMENT = "document"
    ARCHIVE = "archive"
    STREAM_PARTITION = "stream_partition"
    TELEMETRY_BUNDLE = "telemetry_bundle"
    SIMULATED_FILE = "simulated_file"
    CUSTOM = "custom"


class StorageProvider(StrEnum):
    LOCAL = "local"
    S3 = "s3"
    AZURE_BLOB = "azure_blob"
    GOOGLE_CLOUD_STORAGE = "google_cloud_storage"
    SUPABASE_STORAGE = "supabase_storage"
    DATABASE_REFERENCE = "database_reference"
    EXTERNAL_MANAGED = "external_managed"
    CUSTOM = "custom"


class CompressionType(StrEnum):
    NONE = "none"
    GZIP = "gzip"
    ZIP = "zip"
    TAR = "tar"
    TAR_GZIP = "tar_gzip"
    BZ2 = "bz2"
    XZ = "xz"
    CUSTOM = "custom"


class ChecksumAlgorithm(StrEnum):
    SHA256 = "sha256"
    SHA512 = "sha512"
    MD5 = "md5"


class RawObjectStatus(StrEnum):
    REGISTERED = "registered"
    RECEIVING = "receiving"
    RECEIVED = "received"
    VERIFYING = "verifying"
    SEALED = "sealed"
    QUARANTINED = "quarantined"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"
    DELETION_REQUESTED = "deletion_requested"
    DELETED_REFERENCE = "deleted_reference"


class IntegrityStatus(StrEnum):
    UNKNOWN = "unknown"
    PENDING = "pending"
    VERIFIED = "verified"
    MISMATCH = "mismatch"
    CORRUPTED = "corrupted"
    UNAVAILABLE = "unavailable"


class RetentionClass(StrEnum):
    TRANSIENT = "transient"
    STANDARD = "standard"
    EXTENDED = "extended"
    REGULATORY = "regulatory"
    PERMANENT = "permanent"
    CUSTOM = "custom"


class RawRecordStatus(StrEnum):
    REGISTERED = "registered"
    AVAILABLE = "available"
    EXCLUDED = "excluded"
    QUARANTINED = "quarantined"
    SUPERSEDED = "superseded"
    UNAVAILABLE = "unavailable"


class ProcessingRunType(StrEnum):
    INTEGRITY_VERIFICATION = "integrity_verification"
    DECOMPRESSION = "decompression"
    EXTRACTION = "extraction"
    PARSING = "parsing"
    SCHEMA_DISCOVERY = "schema_discovery"
    SEGMENTATION = "segmentation"
    NORMALIZATION = "normalization"
    MAPPING = "mapping"
    TRUST_ASSESSMENT = "trust_assessment"
    CUSTOM = "custom"


class ExecutorType(StrEnum):
    USER = "user"
    SERVICE = "service"
    WORKER = "worker"
    AGENT = "agent"
    SCHEDULED_JOB = "scheduled_job"
    EXTERNAL_SYSTEM = "external_system"
    SIMULATION = "simulation"


class ProcessingRunStatus(StrEnum):
    CREATED = "created"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIALLY_COMPLETED = "partially_completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    QUARANTINED = "quarantined"


class LineageNodeType(StrEnum):
    SOURCE_SYSTEM = "source_system"
    INGESTION_BATCH = "ingestion_batch"
    DATASET = "dataset"
    DATASET_VERSION = "dataset_version"
    RAW_STORAGE_OBJECT = "raw_storage_object"
    RAW_RECORD_REFERENCE = "raw_record_reference"
    PROCESSING_RUN = "processing_run"
    SOURCE_SCHEMA = "source_schema"
    MAPPING_RUN = "mapping_run"
    MAPPING_RECORD_RESULT = "mapping_record_result"
    CANONICAL_ENTITY = "canonical_entity"
    CANONICAL_EVENT = "canonical_event"
    CANONICAL_METRIC = "canonical_metric"
    CUSTOM = "custom"


class LineageNodeStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    UNAVAILABLE = "unavailable"
    ARCHIVED = "archived"


class LineageRelationshipType(StrEnum):
    ORIGINATES_FROM = "originates_from"
    DELIVERED_IN = "delivered_in"
    DESCRIBES = "describes"
    STORED_AS = "stored_as"
    CONTAINS = "contains"
    EXTRACTED_FROM = "extracted_from"
    PARSED_FROM = "parsed_from"
    DERIVED_FROM = "derived_from"
    TRANSFORMED_FROM = "transformed_from"
    VALIDATED_AGAINST = "validated_against"
    SUPERSEDES = "supersedes"
    PRODUCED_BY = "produced_by"
    CONSUMED_BY = "consumed_by"
    MAPPED_BY = "mapped_by"
    CANONICALIZED_AS = "canonicalized_as"
    RESOLVED_TO = "resolved_to"
    LINKED_TO = "linked_to"
    CUSTOM = "custom"


class LineageEventType(StrEnum):
    REGISTERED = "registered"
    RECEIVED = "received"
    CHECKSUM_VERIFIED = "checksum_verified"
    INTEGRITY_MISMATCH = "integrity_mismatch"
    SEALED = "sealed"
    QUARANTINED = "quarantined"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"
    DELETION_REQUESTED = "deletion_requested"
    REFERENCE_DELETED = "reference_deleted"
    LINEAGE_LINK_CREATED = "lineage_link_created"
    PROCESSING_STARTED = "processing_started"
    PROCESSING_COMPLETED = "processing_completed"
    PROCESSING_FAILED = "processing_failed"
    LEGAL_HOLD_APPLIED = "legal_hold_applied"
    LEGAL_HOLD_RELEASED = "legal_hold_released"
    CUSTOM = "custom"


class ActorType(StrEnum):
    USER = "user"
    SERVICE = "service"
    SYSTEM = "system"


class RawStorageObject(Base):
    __tablename__ = "raw_storage_objects"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "source_system_id"],
            ["source_systems.organization_id", "source_systems.id"],
            name="fk_raw_storage_objects_org_source_system",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "ingestion_batch_id"],
            ["ingestion_batches.organization_id", "ingestion_batches.id"],
            name="fk_raw_storage_objects_org_ingestion_batch",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "dataset_version_id"],
            ["dataset_versions.organization_id", "dataset_versions.id"],
            name="fk_raw_storage_objects_org_dataset_version",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "supersedes_raw_object_id"],
            ["raw_storage_objects.organization_id", "raw_storage_objects.id"],
            name="fk_raw_storage_objects_org_supersedes",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "id", name="uq_raw_storage_objects_org_id"),
        UniqueConstraint(
            "organization_id", "object_number", name="uq_raw_objects_organization_number"
        ),
        UniqueConstraint(
            "organization_id", "idempotency_key", name="uq_raw_objects_organization_idempotency"
        ),
        CheckConstraint(
            f"object_type IN ({enum_values(RawObjectType)})", name="ck_raw_object_type"
        ),
        CheckConstraint(
            f"storage_provider IN ({enum_values(StorageProvider)})",
            name="ck_raw_storage_provider",
        ),
        CheckConstraint(
            f"compression_type IN ({enum_values(CompressionType)})",
            name="ck_raw_compression",
        ),
        CheckConstraint(
            f"content_checksum_algorithm IN ({enum_values(ChecksumAlgorithm)})",
            name="ck_raw_checksum_algorithm",
        ),
        CheckConstraint(f"status IN ({enum_values(RawObjectStatus)})", name="ck_raw_status"),
        CheckConstraint(
            f"integrity_status IN ({enum_values(IntegrityStatus)})",
            name="ck_raw_integrity_status",
        ),
        CheckConstraint(
            f"retention_class IN ({enum_values(RetentionClass)})",
            name="ck_raw_retention_class",
        ),
        CheckConstraint(
            "size_bytes >= 0 AND (record_count IS NULL OR record_count >= 0) "
            "AND (column_count IS NULL OR column_count >= 0)",
            name="ck_raw_counts_nonnegative",
        ),
        CheckConstraint(
            "status != 'sealed' OR sealed_at IS NOT NULL", name="ck_raw_sealed_timestamp"
        ),
        CheckConstraint(
            "supersedes_raw_object_id IS NULL OR supersedes_raw_object_id != id",
            name="ck_raw_not_self_superseding",
        ),
        Index("ix_raw_objects_organization_id", "organization_id"),
        Index("ix_raw_objects_source_system_id", "source_system_id"),
        Index("ix_raw_objects_ingestion_batch_id", "ingestion_batch_id"),
        Index("ix_raw_objects_dataset_version_id", "dataset_version_id"),
        Index(
            "ix_raw_storage_objects_org_source_system_id",
            "organization_id",
            "source_system_id",
        ),
        Index(
            "ix_raw_storage_objects_org_ingestion_batch_id",
            "organization_id",
            "ingestion_batch_id",
        ),
        Index(
            "ix_raw_storage_objects_org_dataset_version_id",
            "organization_id",
            "dataset_version_id",
        ),
        Index(
            "ix_raw_storage_objects_org_supersedes_raw_object_id",
            "organization_id",
            "supersedes_raw_object_id",
        ),
        Index("ix_raw_objects_status", "status"),
        Index("ix_raw_objects_integrity_status", "integrity_status"),
        Index("ix_raw_objects_content_checksum", "content_checksum"),
        Index("ix_raw_objects_received_at", "received_at"),
        Index("ix_raw_objects_retention_until", "retention_until"),
        Index("ix_raw_objects_legal_hold", "legal_hold"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    source_system_id: Mapped[UUID] = mapped_column(
        ForeignKey("source_systems.id", ondelete="RESTRICT")
    )
    ingestion_batch_id: Mapped[UUID] = mapped_column(
        ForeignKey("ingestion_batches.id", ondelete="RESTRICT")
    )
    dataset_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="RESTRICT")
    )
    object_number: Mapped[str] = mapped_column(String(120))
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    object_type: Mapped[str] = mapped_column(String(40))
    storage_provider: Mapped[str] = mapped_column(String(40))
    storage_reference: Mapped[str] = mapped_column(String(1000))
    storage_container_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    storage_region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    normalized_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_extension: Mapped[str | None] = mapped_column(String(30), nullable=True)
    media_type: Mapped[str | None] = mapped_column(String(150), nullable=True)
    encoding: Mapped[str | None] = mapped_column(String(50), nullable=True)
    compression_type: Mapped[str] = mapped_column(String(30), default=CompressionType.NONE.value)
    content_checksum_algorithm: Mapped[str] = mapped_column(String(20))
    content_checksum: Mapped[str] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column(Integer)
    record_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    column_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default=RawObjectStatus.REGISTERED.value)
    integrity_status: Mapped[str] = mapped_column(String(30), default=IntegrityStatus.UNKNOWN.value)
    retention_class: Mapped[str] = mapped_column(String(30), default=RetentionClass.STANDARD.value)
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    legal_hold: Mapped[bool] = mapped_column(Boolean, default=False)
    legal_hold_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sealed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    supersedes_raw_object_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("raw_storage_objects.id", ondelete="RESTRICT"), nullable=True
    )
    metadata_json: Mapped[dict[str, object] | None] = mapped_column(portable_json, nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class RawRecordReference(Base):
    __tablename__ = "raw_record_references"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "raw_storage_object_id"],
            ["raw_storage_objects.organization_id", "raw_storage_objects.id"],
            name="fk_raw_record_references_org_raw_storage_object",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "dataset_version_id"],
            ["dataset_versions.organization_id", "dataset_versions.id"],
            name="fk_raw_record_references_org_dataset_version",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "raw_storage_object_id", "record_sequence", name="uq_raw_records_object_sequence"
        ),
        UniqueConstraint(
            "organization_id",
            "id",
            name="uq_raw_record_references_org_id",
        ),
        CheckConstraint("record_sequence > 0", name="ck_raw_record_sequence_positive"),
        CheckConstraint(
            "source_row_number IS NULL OR source_row_number > 0",
            name="ck_raw_record_row_positive",
        ),
        CheckConstraint(
            "source_page_number IS NULL OR source_page_number > 0",
            name="ck_raw_record_page_positive",
        ),
        CheckConstraint(
            f"record_checksum_algorithm IS NULL OR "
            f"record_checksum_algorithm IN ({enum_values(ChecksumAlgorithm)})",
            name="ck_raw_record_checksum_algorithm",
        ),
        CheckConstraint(f"status IN ({enum_values(RawRecordStatus)})", name="ck_raw_record_status"),
        Index("ix_raw_records_organization_id", "organization_id"),
        Index("ix_raw_records_object_id", "raw_storage_object_id"),
        Index("ix_raw_records_dataset_version_id", "dataset_version_id"),
        Index(
            "ix_raw_record_references_org_raw_storage_object_id",
            "organization_id",
            "raw_storage_object_id",
        ),
        Index(
            "ix_raw_record_references_org_dataset_version_id",
            "organization_id",
            "dataset_version_id",
        ),
        Index("ix_raw_records_record_key", "record_key"),
        Index("ix_raw_records_source_event_id", "source_event_id"),
        Index("ix_raw_records_source_timestamp", "source_timestamp"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    raw_storage_object_id: Mapped[UUID] = mapped_column(
        ForeignKey("raw_storage_objects.id", ondelete="RESTRICT")
    )
    dataset_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="RESTRICT")
    )
    record_sequence: Mapped[int] = mapped_column(Integer)
    record_locator: Mapped[str | None] = mapped_column(String(500), nullable=True)
    record_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    record_checksum_algorithm: Mapped[str | None] = mapped_column(String(20), nullable=True)
    record_checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_row_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_sheet_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    source_page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_partition: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_offset: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(30), default=RawRecordStatus.REGISTERED.value)
    metadata_json: Mapped[dict[str, object] | None] = mapped_column(portable_json, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ProcessingRun(Base):
    __tablename__ = "processing_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "ingestion_batch_id"],
            ["ingestion_batches.organization_id", "ingestion_batches.id"],
            name="fk_processing_runs_org_ingestion_batch",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "dataset_version_id"],
            ["dataset_versions.organization_id", "dataset_versions.id"],
            name="fk_processing_runs_org_dataset_version",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "parent_run_id"],
            ["processing_runs.organization_id", "processing_runs.id"],
            name="fk_processing_runs_org_parent_run",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "id", name="uq_processing_runs_org_id"),
        CheckConstraint(f"run_type IN ({enum_values(ProcessingRunType)})", name="ck_run_type"),
        CheckConstraint(f"status IN ({enum_values(ProcessingRunStatus)})", name="ck_run_status"),
        CheckConstraint(
            f"executor_type IN ({enum_values(ExecutorType)})", name="ck_run_executor_type"
        ),
        CheckConstraint(
            "input_count >= 0 AND output_count >= 0 AND warning_count >= 0 AND error_count >= 0",
            name="ck_run_counts_nonnegative",
        ),
        CheckConstraint(
            "parent_run_id IS NULL OR parent_run_id != id", name="ck_run_not_own_parent"
        ),
        CheckConstraint(
            "run_type IN ('integrity_verification', 'custom') "
            "OR ingestion_batch_id IS NOT NULL OR dataset_version_id IS NOT NULL",
            name="ck_processing_runs_data_anchor",
        ),
        Index("ix_processing_runs_organization_id", "organization_id"),
        Index("ix_processing_runs_batch_id", "ingestion_batch_id"),
        Index("ix_processing_runs_dataset_version_id", "dataset_version_id"),
        Index(
            "ix_processing_runs_org_ingestion_batch_id",
            "organization_id",
            "ingestion_batch_id",
        ),
        Index(
            "ix_processing_runs_org_dataset_version_id",
            "organization_id",
            "dataset_version_id",
        ),
        Index(
            "ix_processing_runs_org_parent_run_id",
            "organization_id",
            "parent_run_id",
        ),
        Index("ix_processing_runs_status", "status"),
        Index("ix_processing_runs_run_type", "run_type"),
        Index("ix_processing_runs_correlation_id", "correlation_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    ingestion_batch_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("ingestion_batches.id", ondelete="RESTRICT"), nullable=True
    )
    dataset_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="RESTRICT"), nullable=True
    )
    run_type: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(30), default=ProcessingRunStatus.CREATED.value)
    executor_type: Mapped[str] = mapped_column(String(30))
    executor_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    parent_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("processing_runs.id", ondelete="RESTRICT"), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    input_count: Mapped[int] = mapped_column(Integer, default=0)
    output_count: Mapped[int] = mapped_column(Integer, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    failure_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    parameters_json: Mapped[dict[str, object] | None] = mapped_column(portable_json, nullable=True)
    metrics_json: Mapped[dict[str, object] | None] = mapped_column(portable_json, nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class LineageNode(Base):
    __tablename__ = "lineage_nodes"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_lineage_nodes_org_id"),
        UniqueConstraint(
            "organization_id", "node_type", "entity_id", name="uq_lineage_node_entity"
        ),
        CheckConstraint(
            f"node_type IN ({enum_values(LineageNodeType)})", name="ck_lineage_node_type"
        ),
        CheckConstraint(
            f"status IN ({enum_values(LineageNodeStatus)})", name="ck_lineage_node_status"
        ),
        Index("ix_lineage_nodes_organization_id", "organization_id"),
        Index("ix_lineage_nodes_entity_id", "entity_id"),
        Index("ix_lineage_nodes_node_type", "node_type"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    node_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[UUID] = mapped_column(Uuid)
    entity_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default=LineageNodeStatus.ACTIVE.value)
    metadata_json: Mapped[dict[str, object] | None] = mapped_column(portable_json, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class LineageEdge(Base):
    __tablename__ = "lineage_edges"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "from_node_id"],
            ["lineage_nodes.organization_id", "lineage_nodes.id"],
            name="fk_lineage_edges_org_from_node",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "to_node_id"],
            ["lineage_nodes.organization_id", "lineage_nodes.id"],
            name="fk_lineage_edges_org_to_node",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "processing_run_id"],
            ["processing_runs.organization_id", "processing_runs.id"],
            name="fk_lineage_edges_org_processing_run",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "organization_id",
            "from_node_id",
            "to_node_id",
            "relationship_type",
            "processing_run_key",
            name="uq_lineage_edge_identity",
        ),
        CheckConstraint(
            f"relationship_type IN ({enum_values(LineageRelationshipType)})",
            name="ck_lineage_edge_relationship",
        ),
        CheckConstraint("from_node_id != to_node_id", name="ck_lineage_edge_not_self"),
        CheckConstraint("sequence >= 0", name="ck_lineage_edge_sequence_nonnegative"),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_lineage_edge_confidence",
        ),
        Index("ix_lineage_edges_organization_id", "organization_id"),
        Index("ix_lineage_edges_from_node_id", "from_node_id"),
        Index("ix_lineage_edges_to_node_id", "to_node_id"),
        Index("ix_lineage_edges_relationship_type", "relationship_type"),
        Index("ix_lineage_edges_processing_run_id", "processing_run_id"),
        Index("ix_lineage_edges_org_from_node_id", "organization_id", "from_node_id"),
        Index("ix_lineage_edges_org_to_node_id", "organization_id", "to_node_id"),
        Index(
            "ix_lineage_edges_org_processing_run_id",
            "organization_id",
            "processing_run_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    from_node_id: Mapped[UUID] = mapped_column(ForeignKey("lineage_nodes.id", ondelete="RESTRICT"))
    to_node_id: Mapped[UUID] = mapped_column(ForeignKey("lineage_nodes.id", ondelete="RESTRICT"))
    relationship_type: Mapped[str] = mapped_column(String(40))
    processing_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("processing_runs.id", ondelete="RESTRICT"), nullable=True
    )
    processing_run_key: Mapped[str] = mapped_column(String(36), default="")
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict[str, object] | None] = mapped_column(portable_json, nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class LineageEvent(Base):
    __tablename__ = "lineage_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "processing_run_id"],
            ["processing_runs.organization_id", "processing_runs.id"],
            name="fk_lineage_events_org_processing_run",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            f"event_type IN ({enum_values(LineageEventType)})", name="ck_lineage_event_type"
        ),
        CheckConstraint(
            f"actor_type IN ({enum_values(ActorType)})", name="ck_lineage_event_actor_type"
        ),
        Index("ix_lineage_events_organization_id", "organization_id"),
        Index("ix_lineage_events_entity", "entity_type", "entity_id"),
        Index("ix_lineage_events_processing_run_id", "processing_run_id"),
        Index(
            "ix_lineage_events_org_processing_run_id",
            "organization_id",
            "processing_run_id",
        ),
        Index("ix_lineage_events_occurred_at", "occurred_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    event_type: Mapped[str] = mapped_column(String(40))
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[UUID] = mapped_column(Uuid)
    processing_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("processing_runs.id", ondelete="RESTRICT"), nullable=True
    )
    actor_type: Mapped[str] = mapped_column(String(30), default=ActorType.USER.value)
    actor_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, object] | None] = mapped_column(portable_json, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
