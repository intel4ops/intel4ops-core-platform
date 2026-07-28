from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import PurePath
from urllib.parse import parse_qsl, urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.raw_lineage import (
    ActorType,
    ChecksumAlgorithm,
    CompressionType,
    ExecutorType,
    LineageEventType,
    LineageNodeStatus,
    LineageNodeType,
    LineageRelationshipType,
    ProcessingRunStatus,
    ProcessingRunType,
    RawObjectStatus,
    RawObjectType,
    RawRecordStatus,
    RetentionClass,
    StorageProvider,
)
from app.schemas.source_systems import reject_secret_keys

MAX_METADATA_BYTES = 32_768
MAX_RECORD_BATCH_SIZE = 500
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200
DEFAULT_LINEAGE_DEPTH = 3
MAX_LINEAGE_DEPTH = 10
DEFAULT_LINEAGE_NODES = 100
MAX_LINEAGE_NODES = 500

_CHECKSUM_LENGTHS = {
    ChecksumAlgorithm.SHA256: 64,
    ChecksumAlgorithm.SHA512: 128,
    ChecksumAlgorithm.MD5: 32,
}
_SECRET_QUERY_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "credential",
    "key",
    "password",
    "secret",
    "sig",
    "signature",
    "token",
    "x-amz-credential",
    "x-amz-signature",
    "x-amz-security-token",
}
_SECRET_TEXT = re.compile(
    r"(?i)(bearer\s+|service[_-]?role|jwt[_-]?secret|"
    r"aws_access_key_id|aws_secret_access_key|password\s*=|postgres(?:ql)?://)"
)
_SAFE_MEDIA_TYPE = re.compile(
    r"^[a-zA-Z0-9][a-zA-Z0-9!#$&^_.+-]*/[a-zA-Z0-9][a-zA-Z0-9!#$&^_.+-]*$"
)
_SAFE_ENCODING = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,49}$")
_SAFE_FILENAME = re.compile(r"^[^/\\\x00-\x1f]{1,255}$")


def validate_metadata(value: dict[str, object] | None) -> dict[str, object] | None:
    reject_secret_keys(value)
    if (
        value is not None
        and len(json.dumps(value, separators=(",", ":")).encode()) > MAX_METADATA_BYTES
    ):
        raise ValueError("Metadata exceeds the permitted size")
    return value


def validate_safe_reference(value: str | None) -> str | None:
    if value is None:
        return None
    candidate = value.strip()
    if not candidate or _SECRET_TEXT.search(candidate):
        raise ValueError("Storage reference is not permitted")
    parsed = urlsplit(candidate)
    if parsed.username or parsed.password:
        raise ValueError("Storage reference is not permitted")
    query_keys = {key.lower() for key, _ in parse_qsl(parsed.query, keep_blank_values=True)}
    if query_keys & _SECRET_QUERY_KEYS or any(key.startswith("x-amz-") for key in query_keys):
        raise ValueError("Storage reference is not permitted")
    return candidate


def validate_checksum(algorithm: ChecksumAlgorithm, checksum: str) -> str:
    normalized = checksum.lower()
    required = _CHECKSUM_LENGTHS[algorithm]
    if len(normalized) != required or re.fullmatch(r"[0-9a-f]+", normalized) is None:
        raise ValueError(f"{algorithm.value} checksum must be {required} hexadecimal characters")
    return normalized


class RawStorageObjectCreate(BaseModel):
    source_system_id: UUID
    ingestion_batch_id: UUID
    dataset_version_id: UUID
    object_number: str = Field(
        min_length=1, max_length=120, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$"
    )
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=255)
    object_type: RawObjectType
    storage_provider: StorageProvider
    storage_reference: str = Field(min_length=1, max_length=1000)
    storage_container_reference: str | None = Field(default=None, max_length=500)
    storage_region: str | None = Field(default=None, max_length=100, pattern=r"^[A-Za-z0-9._-]+$")
    original_filename: str | None = None
    normalized_filename: str | None = None
    file_extension: str | None = Field(default=None, max_length=30)
    media_type: str | None = Field(default=None, max_length=150)
    encoding: str | None = Field(default=None, max_length=50)
    compression_type: CompressionType = CompressionType.NONE
    content_checksum_algorithm: ChecksumAlgorithm = ChecksumAlgorithm.SHA256
    content_checksum: str
    size_bytes: int = Field(ge=0)
    record_count: int | None = Field(default=None, ge=0)
    column_count: int | None = Field(default=None, ge=0)
    retention_class: RetentionClass = RetentionClass.STANDARD
    retention_until: datetime | None = None
    received_at: datetime
    supersedes_raw_object_id: UUID | None = None
    metadata_json: dict[str, object] | None = None

    @field_validator("storage_reference", "storage_container_reference")
    @classmethod
    def safe_reference(cls, value: str | None) -> str | None:
        return validate_safe_reference(value)

    @field_validator("original_filename", "normalized_filename")
    @classmethod
    def filename(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if _SAFE_FILENAME.fullmatch(value) is None or PurePath(value).name != value:
            raise ValueError("Filename is not permitted")
        return value

    @field_validator("file_extension")
    @classmethod
    def extension(cls, value: str | None) -> str | None:
        if value is not None and (
            value != value.lower() or re.fullmatch(r"[a-z0-9][a-z0-9._-]*", value) is None
        ):
            raise ValueError("File extension must be lowercase and safe")
        return value

    @field_validator("media_type")
    @classmethod
    def media_type_format(cls, value: str | None) -> str | None:
        if value is not None and _SAFE_MEDIA_TYPE.fullmatch(value) is None:
            raise ValueError("Media type is invalid")
        return value

    @field_validator("encoding")
    @classmethod
    def encoding_format(cls, value: str | None) -> str | None:
        if value is not None and _SAFE_ENCODING.fullmatch(value) is None:
            raise ValueError("Encoding is invalid")
        return value

    @field_validator("received_at", "retention_until")
    @classmethod
    def aware_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() is None:
            raise ValueError("Timestamp must include a timezone")
        return value

    @field_validator("metadata_json")
    @classmethod
    def metadata(cls, value: dict[str, object] | None) -> dict[str, object] | None:
        return validate_metadata(value)

    @model_validator(mode="after")
    def checksum_matches_algorithm(self) -> RawStorageObjectCreate:
        self.content_checksum = validate_checksum(
            self.content_checksum_algorithm, self.content_checksum
        )
        if self.retention_until is not None and self.retention_until < self.received_at:
            raise ValueError("Retention timestamp cannot precede receipt")
        return self


class RawStorageObjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    source_system_id: UUID
    ingestion_batch_id: UUID
    dataset_version_id: UUID
    object_number: str
    object_type: str
    storage_provider: str
    original_filename: str | None
    normalized_filename: str | None
    file_extension: str | None
    media_type: str | None
    encoding: str | None
    compression_type: str
    content_checksum_algorithm: str
    content_checksum: str
    size_bytes: int
    record_count: int | None
    column_count: int | None
    status: str
    integrity_status: str
    retention_class: str
    retention_until: datetime | None
    legal_hold: bool
    legal_hold_reason: str | None
    received_at: datetime
    sealed_at: datetime | None
    verified_at: datetime | None
    supersedes_raw_object_id: UUID | None
    metadata_json: dict[str, object] | None
    created_by_user_id: UUID
    created_at: datetime
    updated_at: datetime


class StatusTransition(BaseModel):
    status: RawObjectStatus
    summary: str | None = Field(default=None, max_length=500)


class IntegrityVerification(BaseModel):
    checksum_algorithm: ChecksumAlgorithm
    checksum: str
    matched: bool

    @model_validator(mode="after")
    def valid_checksum(self) -> IntegrityVerification:
        self.checksum = validate_checksum(self.checksum_algorithm, self.checksum)
        return self


class QuarantineRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class SupersedeRequest(BaseModel):
    superseding_raw_object_id: UUID


class LegalHoldRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class RawRecordReferenceCreate(BaseModel):
    dataset_version_id: UUID
    record_sequence: int = Field(gt=0)
    record_locator: str | None = Field(default=None, max_length=500)
    record_key: str | None = Field(default=None, max_length=255)
    record_checksum_algorithm: ChecksumAlgorithm | None = None
    record_checksum: str | None = None
    source_row_number: int | None = Field(default=None, gt=0)
    source_sheet_name: str | None = Field(default=None, max_length=150)
    source_page_number: int | None = Field(default=None, gt=0)
    source_message_id: str | None = Field(default=None, max_length=255)
    source_event_id: str | None = Field(default=None, max_length=255)
    source_partition: str | None = Field(default=None, max_length=100)
    source_offset: str | None = Field(default=None, max_length=100)
    source_timestamp: datetime | None = None
    status: RawRecordStatus = RawRecordStatus.REGISTERED
    metadata_json: dict[str, object] | None = None

    @field_validator("source_timestamp")
    @classmethod
    def aware_source_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() is None:
            raise ValueError("Timestamp must include a timezone")
        return value

    @field_validator("metadata_json")
    @classmethod
    def metadata(cls, value: dict[str, object] | None) -> dict[str, object] | None:
        return validate_metadata(value)

    @model_validator(mode="after")
    def checksum_pair(self) -> RawRecordReferenceCreate:
        if (self.record_checksum_algorithm is None) != (self.record_checksum is None):
            raise ValueError("Record checksum algorithm and value must be supplied together")
        if self.record_checksum_algorithm is not None and self.record_checksum is not None:
            self.record_checksum = validate_checksum(
                self.record_checksum_algorithm, self.record_checksum
            )
        return self


class RawRecordBatchCreate(BaseModel):
    references: list[RawRecordReferenceCreate] = Field(
        min_length=1, max_length=MAX_RECORD_BATCH_SIZE
    )


class RawRecordReferenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    raw_storage_object_id: UUID
    dataset_version_id: UUID
    record_sequence: int
    record_locator: str | None
    record_key: str | None
    record_checksum_algorithm: str | None
    record_checksum: str | None
    source_row_number: int | None
    source_sheet_name: str | None
    source_page_number: int | None
    source_message_id: str | None
    source_event_id: str | None
    source_partition: str | None
    source_offset: str | None
    source_timestamp: datetime | None
    status: str
    metadata_json: dict[str, object] | None
    created_at: datetime


class ProcessingRunCreate(BaseModel):
    ingestion_batch_id: UUID | None = None
    dataset_version_id: UUID | None = None
    run_type: ProcessingRunType
    executor_type: ExecutorType
    executor_reference: str | None = Field(default=None, max_length=255)
    correlation_id: str | None = Field(default=None, max_length=255)
    parent_run_id: UUID | None = None
    parameters_json: dict[str, object] | None = None

    @field_validator("executor_reference")
    @classmethod
    def safe_executor(cls, value: str | None) -> str | None:
        return validate_safe_reference(value)

    @field_validator("parameters_json")
    @classmethod
    def metadata(cls, value: dict[str, object] | None) -> dict[str, object] | None:
        return validate_metadata(value)

    @model_validator(mode="after")
    def require_data_anchor(self) -> ProcessingRunCreate:
        infrastructure_only = {
            ProcessingRunType.INTEGRITY_VERIFICATION,
            ProcessingRunType.CUSTOM,
        }
        if (
            self.run_type not in infrastructure_only
            and self.ingestion_batch_id is None
            and self.dataset_version_id is None
        ):
            raise ValueError("Data transformation processing runs require a data anchor")
        return self


class ProcessingRunResult(BaseModel):
    input_count: int = Field(default=0, ge=0)
    output_count: int = Field(default=0, ge=0)
    warning_count: int = Field(default=0, ge=0)
    error_count: int = Field(default=0, ge=0)
    metrics_json: dict[str, object] | None = None

    @field_validator("metrics_json")
    @classmethod
    def metadata(cls, value: dict[str, object] | None) -> dict[str, object] | None:
        return validate_metadata(value)


class ProcessingRunFailure(ProcessingRunResult):
    failure_code: str = Field(min_length=1, max_length=100)
    failure_summary: str = Field(min_length=1, max_length=500)


class ProcessingRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    ingestion_batch_id: UUID | None
    dataset_version_id: UUID | None
    run_type: str
    status: str
    correlation_id: str | None
    parent_run_id: UUID | None
    started_at: datetime | None
    completed_at: datetime | None
    failed_at: datetime | None
    input_count: int
    output_count: int
    warning_count: int
    error_count: int
    failure_code: str | None
    failure_summary: str | None
    parameters_json: dict[str, object] | None
    metrics_json: dict[str, object] | None
    created_by_user_id: UUID
    created_at: datetime
    updated_at: datetime


class LineageNodeCreate(BaseModel):
    node_type: LineageNodeType
    entity_id: UUID
    entity_reference: str | None = Field(default=None, max_length=255)
    display_name: str | None = Field(default=None, max_length=255)
    status: LineageNodeStatus = LineageNodeStatus.ACTIVE
    metadata_json: dict[str, object] | None = None

    @field_validator("metadata_json")
    @classmethod
    def metadata(cls, value: dict[str, object] | None) -> dict[str, object] | None:
        return validate_metadata(value)


class LineageNodeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    node_type: str
    entity_id: UUID
    entity_reference: str | None
    display_name: str | None
    status: str
    metadata_json: dict[str, object] | None
    created_at: datetime
    updated_at: datetime


class LineageEdgeCreate(BaseModel):
    from_node_id: UUID
    to_node_id: UUID
    relationship_type: LineageRelationshipType
    processing_run_id: UUID | None = None
    sequence: int = Field(default=0, ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)
    is_primary: bool = False
    effective_at: datetime | None = None
    metadata_json: dict[str, object] | None = None

    @field_validator("metadata_json")
    @classmethod
    def metadata(cls, value: dict[str, object] | None) -> dict[str, object] | None:
        return validate_metadata(value)


class LineageEdgeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    from_node_id: UUID
    to_node_id: UUID
    relationship_type: str
    processing_run_id: UUID | None
    sequence: int
    confidence: float | None
    is_primary: bool
    effective_at: datetime | None
    created_by_user_id: UUID
    created_at: datetime


class LineageEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    event_type: LineageEventType
    entity_type: str
    entity_id: UUID
    processing_run_id: UUID | None
    actor_type: ActorType
    actor_user_id: UUID | None
    occurred_at: datetime
    summary: str | None
    metadata_json: dict[str, object] | None
    created_at: datetime


class LineageGraphRead(BaseModel):
    root_node_id: UUID
    nodes: list[LineageNodeRead]
    edges: list[LineageEdgeRead]
    truncated: bool
    depth_reached: int


class ProcessingRunTransition(BaseModel):
    status: ProcessingRunStatus
