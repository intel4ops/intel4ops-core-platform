from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    code: str
    name: str
    description: str
    status: str


class ProductCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50, pattern=r"^[A-Z][A-Z0-9_-]*$")
    name: str = Field(min_length=1, max_length=150)
    description: str = Field(min_length=1, max_length=4000)


class FeatureRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    key: str
    name: str
    description: str
    status: str


class PlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    code: str
    name: str
    plan_type: str
    status: str


class PlanCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50, pattern=r"^[A-Z][A-Z0-9_-]*$")
    name: str = Field(min_length=1, max_length=150)
    plan_type: str = Field(pattern=r"^(pilot|growth|enterprise|partner|oem)$")


class PlanVersionCreate(BaseModel):
    effective_date: datetime
    expires_date: datetime | None = None
    replaces_plan_version_id: UUID | None = None
    migration_policy: str = Field(default="explicit", pattern=r"^(explicit|renewal|immediate)$")
    terms: dict[str, object] = Field(default_factory=dict)


class PlanVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    plan_id: UUID
    version: int
    effective_date: object
    expires_date: object | None
    replaces_plan_version_id: UUID | None
    migration_policy: str
    terms: dict[str, object]


class SubscriptionCreate(BaseModel):
    plan_version_id: UUID
    idempotency_key: str = Field(min_length=1, max_length=255)
    status: str = Field(pattern=r"^(active|trial|enterprise|partner)$")
    starts_at: datetime
    current_period_start: datetime
    current_period_end: datetime
    renews_at: datetime | None = None
    trial_ends_at: datetime | None = None

    @model_validator(mode="after")
    def valid_period(self) -> "SubscriptionCreate":
        if self.current_period_end <= self.current_period_start:
            raise ValueError("current_period_end must be after current_period_start")
        if self.status == "trial" and self.trial_ends_at is None:
            raise ValueError("trial subscriptions require trial_ends_at")
        return self


class SubscriptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    plan_version_id: UUID
    status: str
    starts_at: datetime
    current_period_start: datetime
    current_period_end: datetime
    renews_at: datetime | None
    trial_ends_at: datetime | None
    cancelled_at: datetime | None


class SubscriptionTransition(BaseModel):
    status: str = Field(pattern=r"^(active|cancelled|expired|suspended|trial|enterprise|partner)$")
    reason: str = Field(min_length=1, max_length=4000)
    trial_ends_at: datetime | None = None


class EntitlementGrant(BaseModel):
    entitlement_type: str = Field(
        pattern=r"^(product|feature|capability|industry_pack|api|limit|add_on)$"
    )
    entitlement_key: str = Field(min_length=1, max_length=150)
    enabled: bool = True
    source: str = Field(default="manual", pattern=r"^(plan|contract|manual|trial)$")
    limit_value: Decimal | None = Field(default=None, ge=0)
    limit_unit: str | None = Field(default=None, max_length=50)
    enforcement_type: str | None = Field(default=None, pattern=r"^(hard|soft|warning|read_only)$")
    effective_at: datetime
    expires_at: datetime | None = None
    idempotency_key: str = Field(min_length=1, max_length=255)


class EntitlementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    entitlement_type: str
    entitlement_key: str
    enabled: bool
    source: str
    limit_value: Decimal | None
    limit_unit: str | None
    enforcement_type: str | None
    effective_at: datetime
    expires_at: datetime | None


class ContractCreate(BaseModel):
    subscription_id: UUID | None = None
    contract_code: str = Field(min_length=1, max_length=100)
    contract_type: str = Field(pattern=r"^(enterprise|partner|oem|standard)$")
    effective_at: datetime
    expires_at: datetime | None = None
    renews_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=4000)


class ContractRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    subscription_id: UUID | None
    contract_code: str
    contract_type: str
    effective_at: datetime
    expires_at: datetime | None
    terminated_at: datetime | None
    notes: str | None


class OverrideCreate(BaseModel):
    entitlement_key: str = Field(min_length=1, max_length=150)
    enabled: bool
    limit_value: Decimal | None = Field(default=None, ge=0)
    enforcement_type: str | None = Field(default=None, pattern=r"^(hard|soft|warning|read_only)$")
    effective_at: datetime
    expires_at: datetime | None = None
    reason: str = Field(min_length=1, max_length=4000)
    idempotency_key: str = Field(min_length=1, max_length=255)


class OverrideRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    contract_id: UUID
    entitlement_key: str
    enabled: bool
    limit_value: Decimal | None
    enforcement_type: str | None
    effective_at: datetime
    expires_at: datetime | None
    reason: str


class UsageEventCreate(BaseModel):
    meter_code: str = Field(min_length=1, max_length=100)
    idempotency_key: str = Field(min_length=1, max_length=255)
    quantity: Decimal = Field(gt=0)
    distinct_key: str | None = Field(default=None, max_length=255)
    currency_code: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    source_type: str = Field(min_length=1, max_length=50)
    source_id: str = Field(min_length=1, max_length=255)
    occurred_at: datetime
    metadata_json: dict[str, object] = Field(default_factory=dict)


class UsageEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    meter_code: str
    quantity: Decimal
    distinct_key: str | None
    currency_code: str | None
    source_type: str
    source_id: str
    occurred_at: datetime


class UsageSummaryRead(BaseModel):
    organization_id: UUID
    meter_code: str
    period_type: str
    starts_at: datetime
    ends_at: datetime
    quantities: dict[str, Decimal]


class LimitStatusRead(BaseModel):
    entitlement_key: str
    meter_code: str
    status: str
    action: str
    current_usage: Decimal
    limit_value: Decimal
    remaining: Decimal


class PackAssignmentCreate(BaseModel):
    pack_code: str = Field(min_length=1, max_length=50)
    effective_at: datetime
    expires_at: datetime | None = None


class PackAssignmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    pack_id: UUID
    status: str
    effective_at: datetime
    expires_at: datetime | None


class FeatureFlagCreate(BaseModel):
    feature_key: str = Field(min_length=1, max_length=150)
    enabled: bool
    effective_at: datetime
    expires_at: datetime | None = None
    reason: str = Field(min_length=1, max_length=4000)


class FeatureFlagRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    feature_id: UUID
    enabled: bool
    effective_at: datetime
    expires_at: datetime | None
    reason: str
