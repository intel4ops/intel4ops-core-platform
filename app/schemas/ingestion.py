from __future__ import annotations

from datetime import datetime
from pathlib import PurePath
from urllib.parse import urlparse
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.ingestion import (
    DatasetStatus,
    DatasetType,
    DatasetVersionStatus,
    IngestionBatchStatus,
    IngestionMethod,
    SchemaStatus,
    TriggerType,
)
from app.models.source_system import DataClassification
from app.schemas.source_systems import reject_secret_keys, validate_timezone


def validate_period(start: datetime | None, end: datetime | None) -> None:
    if start is not None and end is not None and end < start:
        raise ValueError("source_period_end cannot precede source_period_start")


def validate_aware_datetime(value: datetime | None) -> datetime | None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ValueError("timestamp must include a timezone offset")
    return value


def validate_counts(total: int, accepted: int, rejected: int) -> None:
    if accepted + rejected > total:
        raise ValueError("accepted and rejected counts cannot exceed the total count")


def validate_storage_reference(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    parsed = urlparse(normalized)
    if not normalized or any(character.isspace() for character in normalized):
        raise ValueError("storage reference must be opaque")
    if parsed.username or parsed.password or parsed.query:
        raise ValueError("storage reference cannot contain credentials or query parameters")
    return normalized


class IngestionBatchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_system_id: UUID
    batch_number: str = Field(min_length=2, max_length=120, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    ingestion_method: IngestionMethod
    trigger_type: TriggerType
    source_period_start: datetime | None = None
    source_period_end: datetime | None = None
    expected_dataset_count: int | None = Field(default=None, ge=0)
    expected_record_count: int | None = Field(default=None, ge=0)
    checksum: str | None = Field(default=None, max_length=255)
    correlation_id: str | None = Field(default=None, max_length=255)
    external_batch_id: str | None = Field(default=None, max_length=255)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=255)
    storage_reference: str | None = Field(default=None, max_length=500)
    manifest_metadata: dict[str, object] | None = None

    @field_validator("storage_reference")
    @classmethod
    def safe_storage_reference(cls, value: str | None) -> str | None:
        return validate_storage_reference(value)

    @field_validator("source_period_start", "source_period_end")
    @classmethod
    def timezone_aware_period(cls, value: datetime | None) -> datetime | None:
        return validate_aware_datetime(value)

    @field_validator("manifest_metadata")
    @classmethod
    def safe_metadata(cls, value: dict[str, object] | None) -> dict[str, object] | None:
        reject_secret_keys(value)
        return value

    @model_validator(mode="after")
    def valid_source_period(self) -> IngestionBatchCreate:
        validate_period(self.source_period_start, self.source_period_end)
        return self


class BatchTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: IngestionBatchStatus


class BatchCountsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actual_record_count: int = Field(ge=0)
    accepted_record_count: int = Field(ge=0)
    rejected_record_count: int = Field(ge=0)
    warning_count: int = Field(default=0, ge=0)
    error_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def reconciled(self) -> BatchCountsUpdate:
        validate_counts(
            self.actual_record_count,
            self.accepted_record_count,
            self.rejected_record_count,
        )
        return self


class BatchFailure(BaseModel):
    model_config = ConfigDict(extra="forbid")
    failure_code: str = Field(
        min_length=1, max_length=100, pattern=r"^[A-Z0-9]+(?:[_-][A-Z0-9]+)*$"
    )
    failure_summary: str = Field(min_length=1, max_length=1000)

    @field_validator("failure_summary")
    @classmethod
    def sanitize_summary(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if any(character in normalized for character in "\r\n\t"):
            raise ValueError("failure_summary must be plain text")
        return normalized


class IngestionBatchRead(BaseModel):
    id: UUID
    organization_id: UUID
    source_system_id: UUID
    batch_number: str
    ingestion_method: IngestionMethod
    status: IngestionBatchStatus
    trigger_type: TriggerType
    submitted_by_user_id: UUID
    started_at: datetime | None
    completed_at: datetime | None
    failed_at: datetime | None
    received_at: datetime
    source_period_start: datetime | None
    source_period_end: datetime | None
    expected_dataset_count: int | None
    actual_dataset_count: int
    expected_record_count: int | None
    actual_record_count: int
    accepted_record_count: int
    rejected_record_count: int
    warning_count: int
    error_count: int
    checksum: str | None
    correlation_id: str | None
    external_batch_id: str | None
    idempotency_key: str | None
    storage_reference: str | None
    manifest_metadata: dict[str, object] | None
    failure_code: str | None
    failure_summary: str | None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class DatasetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_system_id: UUID
    name: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    description: str | None = None
    domain: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
    dataset_type: DatasetType
    sensitivity: DataClassification = DataClassification.INTERNAL
    primary_time_field: str | None = Field(default=None, max_length=150)
    primary_business_key: str | None = Field(default=None, max_length=150)
    source_object_name: str | None = Field(default=None, max_length=255)
    source_schema_name: str | None = Field(default=None, max_length=255)
    source_table_name: str | None = Field(default=None, max_length=255)
    file_pattern: str | None = Field(default=None, max_length=255)
    default_timezone: str | None = Field(default=None, max_length=100)
    default_currency: str | None = Field(default=None, min_length=3, max_length=3)
    retention_days: int | None = Field(default=None, gt=0)
    metadata_json: dict[str, object] | None = None

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("name cannot be blank")
        return normalized

    @field_validator("default_timezone")
    @classmethod
    def valid_timezone(cls, value: str | None) -> str | None:
        return validate_timezone(value)

    @field_validator("default_currency")
    @classmethod
    def valid_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.upper()
        if not normalized.isascii() or not normalized.isalpha():
            raise ValueError("currency must contain three ASCII letters")
        return normalized

    @field_validator("metadata_json")
    @classmethod
    def safe_metadata(cls, value: dict[str, object] | None) -> dict[str, object] | None:
        reject_secret_keys(value)
        return value


class DatasetUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    code: str | None = Field(
        default=None,
        min_length=2,
        max_length=100,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    description: str | None = None
    domain: str | None = Field(
        default=None,
        min_length=2,
        max_length=100,
        pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$",
    )
    dataset_type: DatasetType | None = None
    sensitivity: DataClassification | None = None
    schema_status: SchemaStatus | None = None
    primary_time_field: str | None = Field(default=None, max_length=150)
    primary_business_key: str | None = Field(default=None, max_length=150)
    source_object_name: str | None = Field(default=None, max_length=255)
    source_schema_name: str | None = Field(default=None, max_length=255)
    source_table_name: str | None = Field(default=None, max_length=255)
    file_pattern: str | None = Field(default=None, max_length=255)
    default_timezone: str | None = Field(default=None, max_length=100)
    default_currency: str | None = Field(default=None, min_length=3, max_length=3)
    retention_days: int | None = Field(default=None, gt=0)
    metadata_json: dict[str, object] | None = None

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str | None) -> str | None:
        return None if value is None else DatasetCreate.trim_name(value)

    @field_validator("default_timezone")
    @classmethod
    def valid_timezone(cls, value: str | None) -> str | None:
        return validate_timezone(value)

    @field_validator("default_currency")
    @classmethod
    def valid_currency(cls, value: str | None) -> str | None:
        return DatasetCreate.valid_currency(value)

    @field_validator("metadata_json")
    @classmethod
    def safe_metadata(cls, value: dict[str, object] | None) -> dict[str, object] | None:
        reject_secret_keys(value)
        return value

    @model_validator(mode="after")
    def reject_null_for_required_fields(self) -> DatasetUpdate:
        required = {
            "name",
            "code",
            "domain",
            "dataset_type",
            "sensitivity",
            "schema_status",
        }
        null_fields = [
            field for field in required & self.model_fields_set if getattr(self, field) is None
        ]
        if null_fields:
            raise ValueError(
                f"cannot set required fields to null: {', '.join(sorted(null_fields))}"
            )
        return self


class DatasetRead(BaseModel):
    id: UUID
    organization_id: UUID
    source_system_id: UUID
    name: str
    code: str
    description: str | None
    domain: str
    dataset_type: DatasetType
    sensitivity: DataClassification
    status: DatasetStatus
    schema_status: SchemaStatus
    primary_time_field: str | None
    primary_business_key: str | None
    source_object_name: str | None
    source_schema_name: str | None
    source_table_name: str | None
    file_pattern: str | None
    default_timezone: str | None
    default_currency: str | None
    retention_days: int | None
    metadata_json: dict[str, object] | None
    created_by_user_id: UUID
    updated_by_user_id: UUID
    created_at: datetime
    updated_at: datetime
    deactivated_at: datetime | None
    model_config = ConfigDict(from_attributes=True)


class DatasetVersionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ingestion_batch_id: UUID
    source_file_name: str | None = Field(default=None, max_length=255)
    source_file_extension: str | None = Field(default=None, max_length=30)
    source_file_size_bytes: int | None = Field(default=None, ge=0)
    source_file_checksum: str | None = Field(default=None, max_length=255)
    media_type: str | None = Field(default=None, max_length=150)
    encoding: str | None = Field(default=None, max_length=50)
    delimiter: str | None = Field(default=None, max_length=10)
    sheet_name: str | None = Field(default=None, max_length=150)
    column_count: int | None = Field(default=None, ge=0)
    storage_reference: str | None = Field(default=None, max_length=500)
    raw_schema_reference: str | None = Field(default=None, max_length=500)
    source_period_start: datetime | None = None
    source_period_end: datetime | None = None
    schema_fingerprint: str | None = Field(default=None, max_length=255)
    metadata_json: dict[str, object] | None = None

    @field_validator("source_file_name")
    @classmethod
    def sanitized_filename(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if (
            not normalized
            or PurePath(normalized).name != normalized
            or any(character in normalized for character in "\\/\0")
        ):
            raise ValueError("source_file_name must be a sanitized filename")
        return normalized

    @field_validator("source_file_extension")
    @classmethod
    def lowercase_extension(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.removeprefix(".")
        if not normalized or normalized != normalized.lower() or not normalized.isalnum():
            raise ValueError("source_file_extension must be lowercase and alphanumeric")
        return normalized

    @field_validator("storage_reference", "raw_schema_reference")
    @classmethod
    def safe_reference(cls, value: str | None) -> str | None:
        return validate_storage_reference(value)

    @field_validator("source_period_start", "source_period_end")
    @classmethod
    def timezone_aware_period(cls, value: datetime | None) -> datetime | None:
        return validate_aware_datetime(value)

    @field_validator("metadata_json")
    @classmethod
    def safe_metadata(cls, value: dict[str, object] | None) -> dict[str, object] | None:
        reject_secret_keys(value)
        return value

    @model_validator(mode="after")
    def valid_source_period(self) -> DatasetVersionCreate:
        validate_period(self.source_period_start, self.source_period_end)
        return self


class DatasetVersionCountsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    record_count: int = Field(ge=0)
    accepted_record_count: int = Field(ge=0)
    rejected_record_count: int = Field(ge=0)
    column_count: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def reconciled(self) -> DatasetVersionCountsUpdate:
        validate_counts(self.record_count, self.accepted_record_count, self.rejected_record_count)
        return self


class DatasetVersionMetadataUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    media_type: str | None = Field(default=None, max_length=150)
    encoding: str | None = Field(default=None, max_length=50)
    delimiter: str | None = Field(default=None, max_length=10)
    sheet_name: str | None = Field(default=None, max_length=150)
    raw_schema_reference: str | None = Field(default=None, max_length=500)
    schema_fingerprint: str | None = Field(default=None, max_length=255)
    metadata_json: dict[str, object] | None = None

    @field_validator("raw_schema_reference")
    @classmethod
    def safe_reference(cls, value: str | None) -> str | None:
        return validate_storage_reference(value)

    @field_validator("metadata_json")
    @classmethod
    def safe_metadata(cls, value: dict[str, object] | None) -> dict[str, object] | None:
        reject_secret_keys(value)
        return value


class DatasetVersionTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: DatasetVersionStatus


class DatasetVersionRead(BaseModel):
    id: UUID
    organization_id: UUID
    dataset_id: UUID
    ingestion_batch_id: UUID
    version_number: int
    status: DatasetVersionStatus
    source_file_name: str | None
    source_file_extension: str | None
    source_file_size_bytes: int | None
    source_file_checksum: str | None
    media_type: str | None
    encoding: str | None
    delimiter: str | None
    sheet_name: str | None
    record_count: int
    accepted_record_count: int
    rejected_record_count: int
    column_count: int | None
    storage_reference: str | None
    raw_schema_reference: str | None
    source_period_start: datetime | None
    source_period_end: datetime | None
    received_at: datetime
    processed_at: datetime | None
    schema_fingerprint: str | None
    metadata_json: dict[str, object] | None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
