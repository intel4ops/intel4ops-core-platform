from datetime import datetime
from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.authorization import (
    OrganizationAccess,
    require_organization_roles,
    require_platform_admin,
)
from app.auth.identity import AuthenticatedUser
from app.auth.permissions import COMMERCIAL_ADMIN_ROLES, COMMERCIAL_READ_ROLES
from app.db.session import get_db
from app.models.commercial import (
    IndustryPackDefinition,
    UsageMeterDefinition,
)
from app.schemas.commercial import (
    ContractCreate,
    ContractRead,
    EntitlementGrant,
    EntitlementRead,
    FeatureFlagCreate,
    FeatureFlagRead,
    FeatureRead,
    LimitStatusRead,
    OverrideCreate,
    OverrideRead,
    PackAssignmentCreate,
    PackAssignmentRead,
    PlanCreate,
    PlanRead,
    PlanVersionCreate,
    PlanVersionRead,
    ProductCreate,
    ProductRead,
    SubscriptionCreate,
    SubscriptionRead,
    SubscriptionTransition,
    UsageEventCreate,
    UsageEventRead,
    UsageSummaryRead,
)
from app.services.commercial_service import (
    CommercialServiceError,
    contract_service,
    entitlement_service,
    feature_flag_service,
    industry_pack_service,
    limit_evaluation_service,
    plan_service,
    product_catalog_service,
    subscription_service,
    usage_aggregation_service,
    usage_meter_service,
)

catalog_router = APIRouter(prefix="/api/v1/commercial")
tenant_router = APIRouter(prefix="/api/v1/organizations/{organization_id}/commercial")


def _raise(exc: CommercialServiceError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status, detail={"code": exc.code, "message": str(exc)}
    ) from exc


@catalog_router.get("/products", response_model=list[ProductRead])
def products(
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_platform_admin),
) -> object:
    return product_catalog_service.products(db)


@catalog_router.post("/products", response_model=ProductRead, status_code=201)
def create_product(
    payload: ProductCreate,
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_platform_admin),
) -> object:
    try:
        return product_catalog_service.create_product(db, payload)
    except CommercialServiceError as exc:
        _raise(exc)


@catalog_router.get("/features", response_model=list[FeatureRead])
def features(
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_platform_admin),
) -> object:
    return product_catalog_service.features(db)


@catalog_router.get("/plans", response_model=list[PlanRead])
def plans(
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_platform_admin),
) -> object:
    return product_catalog_service.plans(db)


@catalog_router.post("/plans", response_model=PlanRead, status_code=201)
def create_plan(
    payload: PlanCreate,
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_platform_admin),
) -> object:
    try:
        return plan_service.create(db, payload)
    except CommercialServiceError as exc:
        _raise(exc)


@catalog_router.get("/plans/{plan_id}/versions", response_model=list[PlanVersionRead])
def plan_versions(
    plan_id: UUID,
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_platform_admin),
) -> object:
    return product_catalog_service.plan_versions(db, plan_id)


@catalog_router.post("/plans/{plan_id}/versions", response_model=PlanVersionRead, status_code=201)
def create_plan_version(
    plan_id: UUID,
    payload: PlanVersionCreate,
    db: Session = Depends(get_db),
    actor: AuthenticatedUser = Depends(require_platform_admin),
) -> object:
    try:
        return plan_service.create_version(db, plan_id, payload, actor.user_id)
    except CommercialServiceError as exc:
        _raise(exc)


@catalog_router.get("/usage-meters")
def usage_meters(
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_platform_admin),
) -> object:
    return list(db.scalars(select(UsageMeterDefinition).order_by(UsageMeterDefinition.code)))


@catalog_router.get("/industry-packs")
def industry_packs(
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_platform_admin),
) -> object:
    return list(db.scalars(select(IndustryPackDefinition).order_by(IndustryPackDefinition.code)))


@tenant_router.post("/subscriptions", response_model=SubscriptionRead, status_code=201)
def create_subscription(
    organization_id: UUID,
    payload: SubscriptionCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*COMMERCIAL_ADMIN_ROLES)),
) -> object:
    try:
        return subscription_service.create(db, organization_id, payload, access.user.user_id)
    except CommercialServiceError as exc:
        _raise(exc)


@tenant_router.get("/subscriptions", response_model=list[SubscriptionRead])
def subscriptions(
    organization_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*COMMERCIAL_READ_ROLES)),
) -> object:
    return subscription_service.list(db, organization_id)


@tenant_router.post("/subscriptions/{subscription_id}/transition", response_model=SubscriptionRead)
def transition_subscription(
    organization_id: UUID,
    subscription_id: UUID,
    payload: SubscriptionTransition,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*COMMERCIAL_ADMIN_ROLES)),
) -> object:
    try:
        return subscription_service.transition(
            db, organization_id, subscription_id, payload, access.user.user_id
        )
    except CommercialServiceError as exc:
        _raise(exc)


@tenant_router.post("/entitlements", response_model=EntitlementRead, status_code=201)
def grant_entitlement(
    organization_id: UUID,
    payload: EntitlementGrant,
    subscription_id: UUID | None = None,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*COMMERCIAL_ADMIN_ROLES)),
) -> object:
    try:
        return entitlement_service.grant(
            db,
            organization_id,
            payload,
            access.user.user_id,
            subscription_id,
        )
    except CommercialServiceError as exc:
        _raise(exc)


@tenant_router.get("/entitlements", response_model=list[EntitlementRead])
def entitlements(
    organization_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*COMMERCIAL_READ_ROLES)),
) -> object:
    return entitlement_service.list(db, organization_id)


@tenant_router.post("/usage-events", response_model=UsageEventRead, status_code=201)
def record_usage(
    organization_id: UUID,
    payload: UsageEventCreate,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*COMMERCIAL_ADMIN_ROLES)),
) -> object:
    try:
        return usage_meter_service.record(db, organization_id, payload)
    except CommercialServiceError as exc:
        _raise(exc)


@tenant_router.get("/usage-events", response_model=list[UsageEventRead])
def usage_events(
    organization_id: UUID,
    meter_code: str | None = None,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*COMMERCIAL_READ_ROLES)),
) -> object:
    return usage_meter_service.list(db, organization_id, meter_code)


@tenant_router.get("/usage-summary", response_model=UsageSummaryRead)
def usage_summary(
    organization_id: UUID,
    meter_code: str,
    period_type: str = Query(
        pattern=r"^(daily|weekly|monthly|billing_period|subscription_period)$"
    ),
    at: datetime = Query(),
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*COMMERCIAL_READ_ROLES)),
) -> object:
    try:
        return usage_aggregation_service.summarize(db, organization_id, meter_code, period_type, at)
    except CommercialServiceError as exc:
        _raise(exc)


@tenant_router.get("/limits/{entitlement_key:path}", response_model=LimitStatusRead)
def limit_status(
    organization_id: UUID,
    entitlement_key: str,
    at: datetime = Query(),
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*COMMERCIAL_READ_ROLES)),
) -> object:
    try:
        return limit_evaluation_service.evaluate(db, organization_id, entitlement_key, at)
    except CommercialServiceError as exc:
        _raise(exc)


@tenant_router.post("/contracts", response_model=ContractRead, status_code=201)
def create_contract(
    organization_id: UUID,
    payload: ContractCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*COMMERCIAL_ADMIN_ROLES)),
) -> object:
    try:
        return contract_service.create(db, organization_id, payload, access.user.user_id)
    except CommercialServiceError as exc:
        _raise(exc)


@tenant_router.get("/contracts", response_model=list[ContractRead])
def contracts(
    organization_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*COMMERCIAL_READ_ROLES)),
) -> object:
    return contract_service.list(db, organization_id)


@tenant_router.post(
    "/contracts/{contract_id}/overrides", response_model=OverrideRead, status_code=201
)
def contract_override(
    organization_id: UUID,
    contract_id: UUID,
    payload: OverrideCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*COMMERCIAL_ADMIN_ROLES)),
) -> object:
    try:
        return contract_service.override(
            db, organization_id, contract_id, payload, access.user.user_id
        )
    except CommercialServiceError as exc:
        _raise(exc)


@tenant_router.post("/industry-packs", response_model=PackAssignmentRead, status_code=201)
def assign_pack(
    organization_id: UUID,
    payload: PackAssignmentCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*COMMERCIAL_ADMIN_ROLES)),
) -> object:
    try:
        return industry_pack_service.assign(db, organization_id, payload, access.user.user_id)
    except CommercialServiceError as exc:
        _raise(exc)


@tenant_router.put("/feature-flags", response_model=FeatureFlagRead)
def set_feature_flag(
    organization_id: UUID,
    payload: FeatureFlagCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*COMMERCIAL_ADMIN_ROLES)),
) -> object:
    try:
        return feature_flag_service.set(db, organization_id, payload, access.user.user_id)
    except CommercialServiceError as exc:
        _raise(exc)
