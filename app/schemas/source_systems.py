from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urlparse
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models.source_system import (
    DataClassification,
    IntegrationMethod,
    SourceEnvironment,
    SourceHealthStatus,
    SourceSystemStatus,
    SourceSystemType,
)

FORBIDDEN_SECRET_KEYS = {
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "private_key",
    "client_secret",
    "access_token",
    "refresh_token",
    "authorization",
    "connection_string",
    "database_url",
    "authentication_header",
    "service_account",
    "service_account_credentials",
    "signed_url",
}


def reject_secret_keys(value: Any) -> Any:
    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key).casefold() in FORBIDDEN_SECRET_KEYS:
                raise ValueError(f"secret-bearing key is not allowed: {key}")
            reject_secret_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            reject_secret_keys(nested)
    return value


def validate_timezone(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    try:
        ZoneInfo(normalized)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("must be a valid IANA timezone") from exc
    return normalized


class SourceSystemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    description: str | None = None
    system_type: SourceSystemType
    provider: str | None = Field(default=None, max_length=100)
    integration_method: IntegrationMethod
    environment: SourceEnvironment = SourceEnvironment.PRODUCTION
    base_url: str | None = Field(default=None, max_length=500)
    database_host_reference: str | None = Field(default=None, max_length=255)
    database_name_reference: str | None = Field(default=None, max_length=255)
    external_system_id: str | None = Field(default=None, max_length=255)
    owner_name: str | None = Field(default=None, max_length=200)
    owner_email: EmailStr | None = None
    data_classification: DataClassification = DataClassification.INTERNAL
    timezone: str | None = Field(default=None, max_length=100)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    credential_reference: str | None = Field(default=None, min_length=1, max_length=500)
    configuration_metadata: dict[str, object] | None = None
    capabilities: list[str] | None = None

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("name cannot be blank")
        return normalized

    @field_validator("provider")
    @classmethod
    def normalize_provider(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if not normalized or not all(
            character.isalnum() or character in {"_", "-", "."} for character in normalized
        ):
            raise ValueError(
                "provider must contain only letters, numbers, dots, dashes, or underscores"
            )
        return normalized

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str | None) -> str | None:
        return validate_timezone(value)

    @field_validator("currency")
    @classmethod
    def uppercase_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.upper()
        if not normalized.isascii() or not normalized.isalpha():
            raise ValueError("currency must contain three ASCII letters")
        return normalized

    @field_validator("base_url")
    @classmethod
    def valid_http_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("base_url must be an HTTP(S) URL")
        return value

    @field_validator("configuration_metadata")
    @classmethod
    def metadata_has_no_secrets(cls, value: dict[str, object] | None) -> dict[str, object] | None:
        reject_secret_keys(value)
        return value

    @field_validator("capabilities")
    @classmethod
    def valid_capabilities(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        normalized = [item.strip() for item in value]
        if any(not item for item in normalized) or len(set(normalized)) != len(normalized):
            raise ValueError("capabilities must contain unique non-empty identifiers")
        return normalized

    @field_validator("credential_reference")
    @classmethod
    def valid_credential_reference(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if any(character.isspace() for character in normalized):
            raise ValueError("credential_reference must be an opaque reference")
        return normalized


class SourceSystemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    code: str | None = Field(
        default=None,
        min_length=2,
        max_length=100,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    description: str | None = None
    system_type: SourceSystemType | None = None
    provider: str | None = Field(default=None, max_length=100)
    integration_method: IntegrationMethod | None = None
    environment: SourceEnvironment | None = None
    status: SourceSystemStatus | None = None
    base_url: str | None = Field(default=None, max_length=500)
    database_host_reference: str | None = Field(default=None, max_length=255)
    database_name_reference: str | None = Field(default=None, max_length=255)
    external_system_id: str | None = Field(default=None, max_length=255)
    owner_name: str | None = Field(default=None, max_length=200)
    owner_email: EmailStr | None = None
    data_classification: DataClassification | None = None
    timezone: str | None = Field(default=None, max_length=100)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    credential_reference: str | None = Field(default=None, min_length=1, max_length=500)
    configuration_metadata: dict[str, object] | None = None
    capabilities: list[str] | None = None

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str | None) -> str | None:
        return None if value is None else SourceSystemCreate.trim_name(value)

    @field_validator("provider")
    @classmethod
    def normalize_provider(cls, value: str | None) -> str | None:
        return SourceSystemCreate.normalize_provider(value)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str | None) -> str | None:
        return validate_timezone(value)

    @field_validator("currency")
    @classmethod
    def uppercase_currency(cls, value: str | None) -> str | None:
        return SourceSystemCreate.uppercase_currency(value)

    @field_validator("base_url")
    @classmethod
    def valid_http_url(cls, value: str | None) -> str | None:
        return SourceSystemCreate.valid_http_url(value)

    @field_validator("configuration_metadata")
    @classmethod
    def metadata_has_no_secrets(cls, value: dict[str, object] | None) -> dict[str, object] | None:
        reject_secret_keys(value)
        return value

    @field_validator("capabilities")
    @classmethod
    def valid_capabilities(cls, value: list[str] | None) -> list[str] | None:
        return SourceSystemCreate.valid_capabilities(value)

    @field_validator("credential_reference")
    @classmethod
    def valid_credential_reference(cls, value: str | None) -> str | None:
        return SourceSystemCreate.valid_credential_reference(value)

    @model_validator(mode="after")
    def reject_null_for_required_fields(self) -> SourceSystemUpdate:
        required = {
            "name",
            "code",
            "system_type",
            "integration_method",
            "environment",
            "status",
            "data_classification",
        }
        null_fields = [
            field for field in required & self.model_fields_set if getattr(self, field) is None
        ]
        if null_fields:
            raise ValueError(
                f"cannot set required fields to null: {', '.join(sorted(null_fields))}"
            )
        return self


class SourceSystemHealthUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    health_status: SourceHealthStatus


class SourceSystemRead(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    code: str
    description: str | None
    system_type: SourceSystemType
    provider: str | None
    integration_method: IntegrationMethod
    environment: SourceEnvironment
    status: SourceSystemStatus
    health_status: SourceHealthStatus
    base_url: str | None
    database_host_reference: str | None
    database_name_reference: str | None
    external_system_id: str | None
    owner_name: str | None
    owner_email: EmailStr | None
    data_classification: DataClassification
    timezone: str | None
    currency: str | None
    last_connection_attempt_at: datetime | None
    last_connection_success_at: datetime | None
    last_connection_failure_at: datetime | None
    last_health_check_at: datetime | None
    failure_count: int
    configuration_metadata: dict[str, object] | None
    capabilities: list[str] | None
    is_active: bool
    created_by_user_id: UUID
    updated_by_user_id: UUID
    created_at: datetime
    updated_at: datetime
    deactivated_at: datetime | None
    model_config = ConfigDict(from_attributes=True)
