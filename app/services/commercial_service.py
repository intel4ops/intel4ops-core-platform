from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.engines.commercial_engine import evaluate_limit, period_bounds
from app.models.commercial import (
    CommercialAuditEvent,
    CommercialContract,
    ContractOverride,
    Entitlement,
    Feature,
    FeatureFlag,
    IndustryPackAssignment,
    IndustryPackDefinition,
    LimitDefinition,
    LimitEvaluation,
    Plan,
    PlanVersion,
    PlanVersionEntitlement,
    Product,
    Subscription,
    UsageEvent,
    UsageMeterDefinition,
)
from app.repositories.commercial_repository import commercial_repository
from app.schemas.commercial import (
    ContractCreate,
    EntitlementGrant,
    FeatureFlagCreate,
    LimitStatusRead,
    OverrideCreate,
    PackAssignmentCreate,
    PlanCreate,
    PlanVersionCreate,
    ProductCreate,
    SubscriptionCreate,
    SubscriptionTransition,
    UsageEventCreate,
    UsageSummaryRead,
)


class CommercialServiceError(ValueError):
    def __init__(self, code: str, message: str, status: int = 422) -> None:
        self.code = code
        self.status = status
        super().__init__(message)


class ProductCatalogService:
    def create_product(self, db: Session, payload: ProductCreate) -> Product:
        if db.scalar(select(Product.id).where(Product.code == payload.code)):
            raise CommercialServiceError(
                "PRODUCT_CODE_CONFLICT", "Product code already exists", 409
            )
        row = Product(**payload.model_dump(), status="active")
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def products(self, db: Session) -> list[Product]:
        return list(db.scalars(select(Product).order_by(Product.code)))

    def features(self, db: Session) -> list[Feature]:
        return list(db.scalars(select(Feature).order_by(Feature.key)))

    def plans(self, db: Session) -> list[Plan]:
        return list(db.scalars(select(Plan).order_by(Plan.code)))

    def plan_versions(self, db: Session, plan_id: UUID) -> list[PlanVersion]:
        return list(
            db.scalars(
                select(PlanVersion)
                .where(PlanVersion.plan_id == plan_id)
                .order_by(PlanVersion.version.desc())
            )
        )


class PlanService:
    def create(self, db: Session, payload: PlanCreate) -> Plan:
        if db.scalar(select(Plan.id).where(Plan.code == payload.code)):
            raise CommercialServiceError("PLAN_CODE_CONFLICT", "Plan code already exists", 409)
        row = Plan(**payload.model_dump(), status="active")
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def create_version(
        self, db: Session, plan_id: UUID, payload: PlanVersionCreate, actor: UUID
    ) -> PlanVersion:
        if db.get(Plan, plan_id) is None:
            raise CommercialServiceError("PLAN_NOT_FOUND", "Plan not found", 404)
        current = db.scalar(
            select(func.max(PlanVersion.version)).where(PlanVersion.plan_id == plan_id)
        )
        if payload.replaces_plan_version_id is not None:
            replaced = db.get(PlanVersion, payload.replaces_plan_version_id)
            if replaced is None or replaced.plan_id != plan_id:
                raise CommercialServiceError(
                    "REPLACEMENT_NOT_FOUND", "Replacement plan version not found", 404
                )
        row = PlanVersion(
            plan_id=plan_id,
            version=(current or 0) + 1,
            effective_date=payload.effective_date.date(),
            expires_date=payload.expires_date.date() if payload.expires_date else None,
            replaces_plan_version_id=payload.replaces_plan_version_id,
            migration_policy=payload.migration_policy,
            terms=payload.terms,
            created_by_user_id=actor,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row


class SubscriptionService:
    def create(
        self, db: Session, org: UUID, payload: SubscriptionCreate, actor: UUID
    ) -> Subscription:
        prior = db.scalar(
            select(Subscription).where(
                Subscription.organization_id == org,
                Subscription.idempotency_key == payload.idempotency_key,
            )
        )
        if prior:
            return prior
        version = db.get(PlanVersion, payload.plan_version_id)
        if version is None:
            raise CommercialServiceError("PLAN_VERSION_NOT_FOUND", "Plan version not found", 404)
        row = Subscription(
            organization_id=org,
            created_by_user_id=actor,
            **payload.model_dump(),
        )
        db.add(row)
        db.flush()
        defaults = list(
            db.scalars(
                select(PlanVersionEntitlement).where(
                    PlanVersionEntitlement.plan_version_id == version.id
                )
            )
        )
        for item in defaults:
            db.add(
                Entitlement(
                    organization_id=org,
                    subscription_id=row.id,
                    entitlement_type=item.entitlement_type,
                    entitlement_key=item.entitlement_key,
                    enabled=item.enabled,
                    source="plan",
                    limit_value=item.limit_value,
                    limit_unit=item.limit_unit,
                    enforcement_type=item.enforcement_type,
                    effective_at=payload.starts_at,
                    expires_at=payload.current_period_end,
                    idempotency_key=f"plan:{row.id}:{item.entitlement_key}",
                    granted_by_user_id=actor,
                )
            )
        _audit(
            db,
            org,
            "subscription_assigned",
            "subscription",
            row.id,
            actor,
            f"audit:{payload.idempotency_key}",
            "Plan version assigned",
        )
        db.commit()
        db.refresh(row)
        return row

    def list(self, db: Session, org: UUID) -> list[Subscription]:
        return list(
            db.scalars(
                select(Subscription)
                .where(Subscription.organization_id == org)
                .order_by(Subscription.created_at.desc())
            )
        )

    def transition(
        self,
        db: Session,
        org: UUID,
        subscription_id: UUID,
        payload: SubscriptionTransition,
        actor: UUID,
    ) -> Subscription:
        row = db.scalar(
            select(Subscription).where(
                Subscription.id == subscription_id,
                Subscription.organization_id == org,
            )
        )
        if row is None:
            raise CommercialServiceError("NOT_FOUND", "Subscription not found", 404)
        row.status = payload.status
        if payload.status == "cancelled":
            row.cancelled_at = datetime.now(UTC)
        if payload.trial_ends_at:
            row.trial_ends_at = payload.trial_ends_at
        _audit(
            db,
            org,
            "subscription_changed",
            "subscription",
            row.id,
            actor,
            f"subscription:{row.id}:{uuid4()}",
            payload.reason,
            {"status": payload.status},
        )
        db.commit()
        db.refresh(row)
        return row


class EntitlementService:
    def grant(
        self,
        db: Session,
        org: UUID,
        payload: EntitlementGrant,
        actor: UUID,
        subscription_id: UUID | None = None,
    ) -> Entitlement:
        prior = db.scalar(
            select(Entitlement).where(
                Entitlement.organization_id == org,
                Entitlement.idempotency_key == payload.idempotency_key,
            )
        )
        if prior:
            return prior
        if subscription_id is not None:
            _require_tenant_row(db, Subscription, org, subscription_id, "Subscription")
        row = Entitlement(
            organization_id=org,
            subscription_id=subscription_id,
            granted_by_user_id=actor,
            **payload.model_dump(),
        )
        db.add(row)
        _audit(
            db,
            org,
            "entitlement_granted",
            "entitlement",
            row.id,
            actor,
            f"audit:{payload.idempotency_key}",
            f"Entitlement {payload.entitlement_key} granted",
        )
        db.commit()
        db.refresh(row)
        return row

    def list(self, db: Session, org: UUID) -> list[Entitlement]:
        return list(
            db.scalars(
                select(Entitlement)
                .where(Entitlement.organization_id == org)
                .order_by(Entitlement.entitlement_key, Entitlement.created_at.desc())
            )
        )

    def require(self, db: Session, org: UUID, key: str) -> Entitlement | None:
        now = datetime.now(UTC)
        subscription = commercial_repository.active_subscription(db, org, now)
        if subscription is None:
            any_subscription = db.scalar(
                select(Subscription.id).where(Subscription.organization_id == org).limit(1)
            )
            if any_subscription is None:
                return None  # Legacy tenant compatibility until commercially assigned.
            raise CommercialServiceError(
                "SUBSCRIPTION_INACTIVE", "An active subscription is required", 403
            )
        if subscription.status == "trial" and subscription.trial_ends_at is not None:
            if _as_utc(subscription.trial_ends_at) <= now:
                raise CommercialServiceError("TRIAL_EXPIRED", "Trial has expired", 403)
        override = db.scalar(
            select(ContractOverride)
            .where(
                ContractOverride.organization_id == org,
                ContractOverride.entitlement_key == key,
                ContractOverride.effective_at <= now,
                (ContractOverride.expires_at.is_(None) | (ContractOverride.expires_at > now)),
            )
            .order_by(ContractOverride.created_at.desc())
        )
        if override is not None:
            if not override.enabled:
                raise CommercialServiceError("ENTITLEMENT_DISABLED", "Entitlement is disabled", 403)
        entitlement = commercial_repository.active_entitlement(db, org, key, now)
        if entitlement is None and override is None:
            raise CommercialServiceError(
                "ENTITLEMENT_REQUIRED", f"Entitlement {key} is required", 403
            )
        return entitlement


class UsageMeterService:
    def record(self, db: Session, org: UUID, payload: UsageEventCreate) -> UsageEvent:
        prior = db.scalar(
            select(UsageEvent).where(
                UsageEvent.organization_id == org,
                UsageEvent.idempotency_key == payload.idempotency_key,
            )
        )
        if prior:
            return prior
        meter = db.scalar(
            select(UsageMeterDefinition).where(
                UsageMeterDefinition.code == payload.meter_code,
                UsageMeterDefinition.active.is_(True),
            )
        )
        if meter is None:
            raise CommercialServiceError("METER_NOT_FOUND", "Usage meter not found", 404)
        if payload.currency_code and meter.currency_behavior == "not_applicable":
            raise CommercialServiceError(
                "CURRENCY_NOT_ALLOWED", "This usage meter does not accept currency"
            )
        row = UsageEvent(organization_id=org, **payload.model_dump())
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def list(self, db: Session, org: UUID, meter: str | None = None) -> list[UsageEvent]:
        query = select(UsageEvent).where(UsageEvent.organization_id == org)
        if meter:
            query = query.where(UsageEvent.meter_code == meter)
        return list(db.scalars(query.order_by(UsageEvent.occurred_at.desc())))


class UsageAggregationService:
    def summarize(
        self,
        db: Session,
        org: UUID,
        meter_code: str,
        period_type: str,
        moment: datetime,
    ) -> UsageSummaryRead:
        meter = db.scalar(
            select(UsageMeterDefinition).where(UsageMeterDefinition.code == meter_code)
        )
        if meter is None:
            raise CommercialServiceError("METER_NOT_FOUND", "Usage meter not found", 404)
        if period_type in {"billing_period", "subscription_period"}:
            subscription = commercial_repository.active_subscription(db, org, moment)
            if subscription is None:
                raise CommercialServiceError(
                    "SUBSCRIPTION_INACTIVE", "An active subscription is required", 403
                )
            start = _as_utc(subscription.current_period_start)
            end = _as_utc(subscription.current_period_end)
        else:
            start, end = period_bounds(period_type, moment)
        events = list(
            db.scalars(
                select(UsageEvent).where(
                    UsageEvent.organization_id == org,
                    UsageEvent.meter_code == meter_code,
                    UsageEvent.occurred_at >= start,
                    UsageEvent.occurred_at < end,
                )
            )
        )
        grouped: dict[str, list[UsageEvent]] = defaultdict(list)
        for item in events:
            grouped[item.currency_code or "NON_CURRENCY"].append(item)
        quantities: dict[str, Decimal] = {}
        for currency, items in grouped.items():
            if meter.aggregation == "maximum":
                quantities[currency] = max((item.quantity for item in items), default=Decimal("0"))
            elif meter.aggregation == "distinct":
                quantities[currency] = Decimal(
                    len({item.distinct_key for item in items if item.distinct_key})
                )
            else:
                quantities[currency] = sum((item.quantity for item in items), start=Decimal("0"))
        if not quantities:
            quantities["NON_CURRENCY"] = Decimal("0")
        return UsageSummaryRead(
            organization_id=org,
            meter_code=meter_code,
            period_type=period_type,
            starts_at=start,
            ends_at=end,
            quantities=quantities,
        )


class LimitEvaluationService:
    def evaluate(
        self, db: Session, org: UUID, entitlement_key: str, moment: datetime
    ) -> LimitStatusRead:
        entitlement = entitlement_service.require(db, org, entitlement_key)
        if entitlement is None or entitlement.limit_value is None:
            raise CommercialServiceError("LIMIT_NOT_CONFIGURED", "Limit is not configured", 404)
        definition = db.scalar(
            select(LimitDefinition).where(LimitDefinition.entitlement_key == entitlement_key)
        )
        if definition is None:
            raise CommercialServiceError("LIMIT_NOT_FOUND", "Limit definition not found", 404)
        summary = usage_aggregation_service.summarize(
            db, org, definition.meter_code, definition.default_reset_period, moment
        )
        usage = sum(summary.quantities.values(), start=Decimal("0"))
        override = db.scalar(
            select(ContractOverride)
            .where(
                ContractOverride.organization_id == org,
                ContractOverride.entitlement_key == entitlement_key,
                ContractOverride.enabled.is_(True),
                ContractOverride.effective_at <= moment,
                (ContractOverride.expires_at.is_(None) | (ContractOverride.expires_at > moment)),
            )
            .order_by(ContractOverride.created_at.desc())
        )
        limit_value = (
            override.limit_value
            if override is not None and override.limit_value is not None
            else entitlement.limit_value
        )
        enforcement_type = (
            override.enforcement_type
            if override is not None and override.enforcement_type is not None
            else entitlement.enforcement_type
        )
        result = evaluate_limit(
            usage,
            limit_value,
            enforcement_type or definition.default_enforcement_type,
            warning_percentage=definition.warning_percentage,
            grace_percentage=definition.grace_percentage,
        )
        db.add(
            LimitEvaluation(
                organization_id=org,
                entitlement_key=entitlement_key,
                meter_code=definition.meter_code,
                current_usage=result.current_usage,
                limit_value=result.limit_value,
                status=result.status.value,
                enforcement_action=result.action,
            )
        )
        db.commit()
        return LimitStatusRead(
            entitlement_key=entitlement_key,
            meter_code=definition.meter_code,
            status=result.status.value,
            action=result.action,
            current_usage=result.current_usage,
            limit_value=result.limit_value,
            remaining=result.remaining,
        )


class ContractService:
    def create(
        self, db: Session, org: UUID, payload: ContractCreate, actor: UUID
    ) -> CommercialContract:
        if payload.subscription_id:
            _require_tenant_row(db, Subscription, org, payload.subscription_id, "Subscription")
        row = CommercialContract(
            organization_id=org, created_by_user_id=actor, **payload.model_dump()
        )
        db.add(row)
        db.flush()
        _audit(
            db,
            org,
            "contract_created",
            "contract",
            row.id,
            actor,
            f"contract:{row.id}",
            "Commercial contract created",
        )
        db.commit()
        db.refresh(row)
        return row

    def list(self, db: Session, org: UUID) -> list[CommercialContract]:
        return list(
            db.scalars(select(CommercialContract).where(CommercialContract.organization_id == org))
        )

    def override(
        self,
        db: Session,
        org: UUID,
        contract_id: UUID,
        payload: OverrideCreate,
        actor: UUID,
    ) -> ContractOverride:
        _require_tenant_row(db, CommercialContract, org, contract_id, "Contract")
        prior = db.scalar(
            select(ContractOverride).where(
                ContractOverride.organization_id == org,
                ContractOverride.idempotency_key == payload.idempotency_key,
            )
        )
        if prior:
            return prior
        row = ContractOverride(
            organization_id=org,
            contract_id=contract_id,
            approved_by_user_id=actor,
            **payload.model_dump(),
        )
        db.add(row)
        _audit(
            db,
            org,
            "contract_override_applied",
            "contract_override",
            row.id,
            actor,
            f"audit:{payload.idempotency_key}",
            payload.reason,
        )
        db.commit()
        db.refresh(row)
        return row


class IndustryPackService:
    def assign(
        self, db: Session, org: UUID, payload: PackAssignmentCreate, actor: UUID
    ) -> IndustryPackAssignment:
        pack = db.scalar(
            select(IndustryPackDefinition).where(IndustryPackDefinition.code == payload.pack_code)
        )
        if pack is None:
            raise CommercialServiceError("PACK_NOT_FOUND", "Industry pack not found", 404)
        entitlement_service.require(db, org, pack.entitlement_key)
        row = db.scalar(
            select(IndustryPackAssignment).where(
                IndustryPackAssignment.organization_id == org,
                IndustryPackAssignment.pack_id == pack.id,
            )
        )
        if row is None:
            row = IndustryPackAssignment(
                organization_id=org,
                pack_id=pack.id,
                assigned_by_user_id=actor,
                status="active",
                effective_at=payload.effective_at,
                expires_at=payload.expires_at,
            )
            db.add(row)
        else:
            row.status = "active"
            row.effective_at = payload.effective_at
            row.expires_at = payload.expires_at
        _audit(
            db,
            org,
            "industry_pack_enabled",
            "industry_pack_assignment",
            row.id,
            actor,
            f"pack:{org}:{pack.code}:{uuid4()}",
            f"Industry pack {pack.code} enabled",
        )
        db.commit()
        db.refresh(row)
        return row


class FeatureFlagService:
    def set(self, db: Session, org: UUID, payload: FeatureFlagCreate, actor: UUID) -> FeatureFlag:
        feature = db.scalar(select(Feature).where(Feature.key == payload.feature_key))
        if feature is None:
            raise CommercialServiceError("FEATURE_NOT_FOUND", "Feature not found", 404)
        if payload.enabled:
            entitlement_service.require(db, org, payload.feature_key)
        row = db.scalar(
            select(FeatureFlag).where(
                FeatureFlag.organization_id == org,
                FeatureFlag.feature_id == feature.id,
            )
        )
        values = payload.model_dump(exclude={"feature_key"})
        if row is None:
            row = FeatureFlag(
                organization_id=org,
                feature_id=feature.id,
                updated_by_user_id=actor,
                **values,
            )
            db.add(row)
        else:
            for key, value in values.items():
                setattr(row, key, value)
            row.updated_by_user_id = actor
        _audit(
            db,
            org,
            "feature_enabled" if payload.enabled else "feature_disabled",
            "feature_flag",
            row.id,
            actor,
            f"feature:{org}:{feature.key}:{uuid4()}",
            payload.reason,
        )
        db.commit()
        db.refresh(row)
        return row


def _require_tenant_row(
    db: Session, model: type[object], org: UUID, row_id: UUID, label: str
) -> None:
    row = db.scalar(
        select(model).where(
            getattr(model, "id") == row_id,
            getattr(model, "organization_id") == org,
        )
    )
    if row is None:
        raise CommercialServiceError("NOT_FOUND", f"{label} not found", 404)


def _audit(
    db: Session,
    org: UUID,
    event_type: str,
    entity_type: str,
    entity_id: object,
    actor: UUID,
    key: str,
    reason: str,
    payload: dict[str, object] | None = None,
) -> None:
    db.add(
        CommercialAuditEvent(
            organization_id=org,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=str(entity_id),
            actor_user_id=actor,
            idempotency_key=key,
            reason=reason,
            event_payload=payload or {},
        )
    )


product_catalog_service = ProductCatalogService()
plan_service = PlanService()
subscription_service = SubscriptionService()
entitlement_service = EntitlementService()
usage_meter_service = UsageMeterService()
usage_aggregation_service = UsageAggregationService()
limit_evaluation_service = LimitEvaluationService()
contract_service = ContractService()
industry_pack_service = IndustryPackService()
feature_flag_service = FeatureFlagService()


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
