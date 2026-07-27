from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
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
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.entities import portable_json, utc_now


class Product(Base):
    __tablename__ = "products"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ProductVersion(Base):
    __tablename__ = "product_versions"
    __table_args__ = (UniqueConstraint("product_id", "version", name="uq_product_version"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    product_id: Mapped[UUID] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    version: Mapped[int] = mapped_column(Integer)
    effective_date: Mapped[date] = mapped_column(Date)
    expires_date: Mapped[date | None] = mapped_column(Date)
    specification: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Feature(Base):
    __tablename__ = "features"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    key: Mapped[str] = mapped_column(String(150), unique=True)
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Plan(Base):
    __tablename__ = "plans"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(150))
    plan_type: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(30), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class PlanVersion(Base):
    __tablename__ = "plan_versions"
    __table_args__ = (
        UniqueConstraint("plan_id", "version", name="uq_plan_version"),
        CheckConstraint("version > 0", name="ck_plan_version_positive"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    plan_id: Mapped[UUID] = mapped_column(ForeignKey("plans.id", ondelete="RESTRICT"))
    version: Mapped[int] = mapped_column(Integer)
    effective_date: Mapped[date] = mapped_column(Date)
    expires_date: Mapped[date | None] = mapped_column(Date)
    replaces_plan_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("plan_versions.id", ondelete="RESTRICT")
    )
    migration_policy: Mapped[str] = mapped_column(String(40), default="explicit")
    terms: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    created_by_user_id: Mapped[UUID | None] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class PlanVersionEntitlement(Base):
    __tablename__ = "plan_version_entitlements"
    __table_args__ = (
        UniqueConstraint("plan_version_id", "entitlement_key", name="uq_plan_version_entitlement"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    plan_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("plan_versions.id", ondelete="CASCADE")
    )
    entitlement_type: Mapped[str] = mapped_column(String(40))
    entitlement_key: Mapped[str] = mapped_column(String(150))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    limit_value: Mapped[Decimal | None] = mapped_column(Numeric(38, 12))
    limit_unit: Mapped[str | None] = mapped_column(String(50))
    enforcement_type: Mapped[str | None] = mapped_column(String(30))
    reset_period: Mapped[str | None] = mapped_column(String(30))
    metadata_json: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        UniqueConstraint("organization_id", "idempotency_key", name="uq_subscription_idempotency"),
        Index("ix_subscription_org_status", "organization_id", "status"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    plan_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("plan_versions.id", ondelete="RESTRICT")
    )
    idempotency_key: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(30))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    current_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    current_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    renews_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class CommercialContract(Base):
    __tablename__ = "contracts"
    __table_args__ = (
        UniqueConstraint("organization_id", "contract_code", name="uq_contract_org_code"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    subscription_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="RESTRICT")
    )
    contract_code: Mapped[str] = mapped_column(String(100))
    contract_type: Mapped[str] = mapped_column(String(40))
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    renews_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    terminated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ContractOverride(Base):
    __tablename__ = "contract_overrides"
    __table_args__ = (
        UniqueConstraint("organization_id", "idempotency_key", name="uq_contract_override_key"),
        Index("ix_contract_override_org_key", "organization_id", "entitlement_key"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    contract_id: Mapped[UUID] = mapped_column(ForeignKey("contracts.id", ondelete="CASCADE"))
    entitlement_key: Mapped[str] = mapped_column(String(150))
    enabled: Mapped[bool] = mapped_column(Boolean)
    limit_value: Mapped[Decimal | None] = mapped_column(Numeric(38, 12))
    enforcement_type: Mapped[str | None] = mapped_column(String(30))
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(String(255))
    approved_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Entitlement(Base):
    __tablename__ = "entitlements"
    __table_args__ = (
        UniqueConstraint("organization_id", "idempotency_key", name="uq_entitlement_idempotency"),
        Index("ix_entitlement_org_key", "organization_id", "entitlement_key"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    subscription_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="CASCADE")
    )
    entitlement_type: Mapped[str] = mapped_column(String(40))
    entitlement_key: Mapped[str] = mapped_column(String(150))
    enabled: Mapped[bool] = mapped_column(Boolean)
    source: Mapped[str] = mapped_column(String(30))
    limit_value: Mapped[Decimal | None] = mapped_column(Numeric(38, 12))
    limit_unit: Mapped[str | None] = mapped_column(String(50))
    enforcement_type: Mapped[str | None] = mapped_column(String(30))
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    idempotency_key: Mapped[str] = mapped_column(String(255))
    granted_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class UsageMeterDefinition(Base):
    __tablename__ = "usage_meter_definitions"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(100), unique=True)
    product: Mapped[str] = mapped_column(String(100))
    meter_kind: Mapped[str] = mapped_column(String(20))
    unit: Mapped[str] = mapped_column(String(50))
    aggregation: Mapped[str] = mapped_column(String(30))
    currency_behavior: Mapped[str] = mapped_column(String(30), default="not_applicable")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class UsageEvent(Base):
    __tablename__ = "usage_events"
    __table_args__ = (
        UniqueConstraint("organization_id", "idempotency_key", name="uq_usage_event_key"),
        Index("ix_usage_event_org_meter_time", "organization_id", "meter_code", "occurred_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    meter_code: Mapped[str] = mapped_column(
        ForeignKey("usage_meter_definitions.code", ondelete="RESTRICT")
    )
    idempotency_key: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[Decimal] = mapped_column(Numeric(38, 12))
    distinct_key: Mapped[str | None] = mapped_column(String(255))
    currency_code: Mapped[str | None] = mapped_column(String(3))
    source_type: Mapped[str] = mapped_column(String(50))
    source_id: Mapped[str] = mapped_column(String(255))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class UsagePeriod(Base):
    __tablename__ = "usage_periods"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "meter_code",
            "period_type",
            "starts_at",
            "currency_code",
            name="uq_usage_period",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    meter_code: Mapped[str] = mapped_column(
        ForeignKey("usage_meter_definitions.code", ondelete="RESTRICT")
    )
    period_type: Mapped[str] = mapped_column(String(30))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    quantity: Mapped[Decimal] = mapped_column(Numeric(38, 12))
    currency_code: Mapped[str | None] = mapped_column(String(3), nullable=True)
    event_count: Mapped[int] = mapped_column(Integer)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class IndustryPackDefinition(Base):
    __tablename__ = "industry_pack_definitions"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(150))
    entitlement_key: Mapped[str] = mapped_column(String(150), unique=True)
    status: Mapped[str] = mapped_column(String(30))


class IndustryPackAssignment(Base):
    __tablename__ = "industry_pack_assignments"
    __table_args__ = (
        UniqueConstraint("organization_id", "pack_id", name="uq_industry_pack_assignment"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    pack_id: Mapped[UUID] = mapped_column(
        ForeignKey("industry_pack_definitions.id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(String(30))
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    assigned_by_user_id: Mapped[UUID] = mapped_column(Uuid)


class FeatureFlag(Base):
    __tablename__ = "feature_flags"
    __table_args__ = (
        UniqueConstraint("organization_id", "feature_id", name="uq_feature_flag_org"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    feature_id: Mapped[UUID] = mapped_column(ForeignKey("features.id", ondelete="RESTRICT"))
    enabled: Mapped[bool] = mapped_column(Boolean)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(Text)
    updated_by_user_id: Mapped[UUID] = mapped_column(Uuid)


class LimitDefinition(Base):
    __tablename__ = "limit_definitions"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    entitlement_key: Mapped[str] = mapped_column(String(150), unique=True)
    meter_code: Mapped[str] = mapped_column(
        ForeignKey("usage_meter_definitions.code", ondelete="RESTRICT")
    )
    default_enforcement_type: Mapped[str] = mapped_column(String(30))
    default_reset_period: Mapped[str] = mapped_column(String(30))
    warning_percentage: Mapped[Decimal] = mapped_column(Numeric(8, 5), default=Decimal("0.8"))
    grace_percentage: Mapped[Decimal] = mapped_column(Numeric(8, 5), default=Decimal("0"))


class LimitEvaluation(Base):
    __tablename__ = "limit_evaluations"
    __table_args__ = (
        Index(
            "ix_limit_evaluation_org_key_time", "organization_id", "entitlement_key", "evaluated_at"
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    entitlement_key: Mapped[str] = mapped_column(String(150))
    meter_code: Mapped[str] = mapped_column(String(100))
    current_usage: Mapped[Decimal] = mapped_column(Numeric(38, 12))
    limit_value: Mapped[Decimal] = mapped_column(Numeric(38, 12))
    status: Mapped[str] = mapped_column(String(30))
    enforcement_action: Mapped[str] = mapped_column(String(30))
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class CommercialAuditEvent(Base):
    __tablename__ = "commercial_audit_events"
    __table_args__ = (
        UniqueConstraint("organization_id", "idempotency_key", name="uq_commercial_audit_key"),
        Index("ix_commercial_audit_org_time", "organization_id", "occurred_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    event_type: Mapped[str] = mapped_column(String(60))
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[str] = mapped_column(String(255))
    actor_user_id: Mapped[UUID] = mapped_column(Uuid)
    idempotency_key: Mapped[str] = mapped_column(String(255))
    reason: Mapped[str] = mapped_column(Text)
    event_payload: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


def _immutable(*_: object) -> None:
    raise ValueError("commercial history records are immutable")


for immutable_model in (
    ProductVersion,
    PlanVersion,
    ContractOverride,
    Entitlement,
    UsageEvent,
    CommercialAuditEvent,
):
    event.listen(immutable_model, "before_update", _immutable)
    event.listen(immutable_model, "before_delete", _immutable)
