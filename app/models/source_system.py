from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.entities import Organization, utc_now

portable_json = JSON().with_variant(JSONB(), "postgresql")


class SourceSystemType(StrEnum):
    ERP = "erp"
    ACCOUNTING = "accounting"
    CRM = "crm"
    CMMS = "cmms"
    EAM = "eam"
    HRMS = "hrms"
    PAYROLL = "payroll"
    INVENTORY = "inventory"
    PROCUREMENT = "procurement"
    POINT_OF_SALE = "point_of_sale"
    BANKING = "banking"
    PAYMENT_PROCESSOR = "payment_processor"
    SPREADSHEET = "spreadsheet"
    FLAT_FILE = "flat_file"
    DATABASE = "database"
    API = "api"
    SCADA = "scada"
    IOT = "iot"
    GPS_TELEMATICS = "gps_telematics"
    FLEET_MANAGEMENT = "fleet_management"
    TICKETING = "ticketing"
    SCHEDULING = "scheduling"
    DOCUMENT_REPOSITORY = "document_repository"
    EMAIL = "email"
    CUSTOM = "custom"


class IntegrationMethod(StrEnum):
    API = "api"
    DATABASE = "database"
    FILE_UPLOAD = "file_upload"
    FILE_DROP = "file_drop"
    SFTP = "sftp"
    WEBHOOK = "webhook"
    MESSAGE_QUEUE = "message_queue"
    EMAIL_INGESTION = "email_ingestion"
    MANUAL = "manual"
    DEVICE_STREAM = "device_stream"
    CUSTOM = "custom"


class SourceEnvironment(StrEnum):
    PRODUCTION = "production"
    STAGING = "staging"
    DEVELOPMENT = "development"
    TEST = "test"
    SANDBOX = "sandbox"


class SourceSystemStatus(StrEnum):
    DRAFT = "draft"
    CONFIGURED = "configured"
    VALIDATING = "validating"
    ACTIVE = "active"
    PAUSED = "paused"
    FAILED = "failed"
    DECOMMISSIONED = "decommissioned"


DOWNSTREAM_CREATION_SOURCE_STATUSES = frozenset({SourceSystemStatus.ACTIVE.value})


class SourceHealthStatus(StrEnum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNAVAILABLE = "unavailable"


class DataClassification(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


def enum_values(enum_type: type[StrEnum]) -> str:
    return ", ".join(f"'{item.value}'" for item in enum_type)


class SourceSystem(Base):
    __tablename__ = "source_systems"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_source_systems_organization_code"),
        CheckConstraint("failure_count >= 0", name="ck_source_systems_failure_count"),
        CheckConstraint(
            f"system_type IN ({enum_values(SourceSystemType)})",
            name="ck_source_systems_system_type",
        ),
        CheckConstraint(
            f"integration_method IN ({enum_values(IntegrationMethod)})",
            name="ck_source_systems_integration_method",
        ),
        CheckConstraint(
            f"environment IN ({enum_values(SourceEnvironment)})",
            name="ck_source_systems_environment",
        ),
        CheckConstraint(
            f"status IN ({enum_values(SourceSystemStatus)})",
            name="ck_source_systems_status",
        ),
        CheckConstraint(
            f"health_status IN ({enum_values(SourceHealthStatus)})",
            name="ck_source_systems_health_status",
        ),
        CheckConstraint(
            f"data_classification IN ({enum_values(DataClassification)})",
            name="ck_source_systems_data_classification",
        ),
        Index("ix_source_systems_organization_id", "organization_id"),
        Index("ix_source_systems_system_type", "system_type"),
        Index("ix_source_systems_status", "status"),
        Index("ix_source_systems_health_status", "health_status"),
        Index("ix_source_systems_provider", "provider"),
        Index("ix_source_systems_is_active", "is_active"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    system_type: Mapped[str] = mapped_column(String(50))
    provider: Mapped[str | None] = mapped_column(String(100), nullable=True)
    integration_method: Mapped[str] = mapped_column(String(50))
    environment: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), default=SourceSystemStatus.DRAFT.value)
    health_status: Mapped[str] = mapped_column(String(30), default=SourceHealthStatus.UNKNOWN.value)
    base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    database_host_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    database_name_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_system_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    owner_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    owner_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    data_classification: Mapped[str] = mapped_column(
        String(30), default=DataClassification.INTERNAL.value
    )
    timezone: Mapped[str | None] = mapped_column(String(100), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    credential_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_connection_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_connection_success_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_connection_failure_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_health_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    configuration_metadata: Mapped[dict[str, object] | None] = mapped_column(
        portable_json, nullable=True
    )
    capabilities: Mapped[list[str] | None] = mapped_column(portable_json, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    updated_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    organization: Mapped[Organization] = relationship(back_populates="source_systems")
