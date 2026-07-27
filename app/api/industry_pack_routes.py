from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.authorization import (
    OrganizationAccess,
    require_organization_roles,
    require_platform_admin,
)
from app.auth.identity import AuthenticatedUser
from app.auth.permissions import COMMERCIAL_ADMIN_ROLES, COMMERCIAL_READ_ROLES
from app.db.session import get_db
from app.schemas.industry_packs import (
    PackAssignmentRead,
    PackAssignmentRequest,
    PackComponentRead,
    PackComponentWrite,
    PackCreate,
    PackExecutionCreate,
    PackExecutionRead,
    PackRead,
    PackTransition,
    PackVersionCreate,
    PackVersionRead,
)
from app.services.commercial_service import CommercialServiceError
from app.services.industry_pack_service import governance_service, tenant_industry_pack_service

catalog_router = APIRouter(prefix="/api/v1/industry-packs", tags=["industry-packs"])
tenant_router = APIRouter(
    prefix="/api/v1/organizations/{organization_id}/industry-packs", tags=["industry-packs"]
)


def _raise(exc: CommercialServiceError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status, detail={"code": exc.code, "message": str(exc)}
    ) from exc


@catalog_router.get("", response_model=list[PackRead])
def catalog(
    db: Session = Depends(get_db), _: AuthenticatedUser = Depends(require_platform_admin)
) -> object:
    return governance_service.catalog(db)


@catalog_router.post("", response_model=PackRead, status_code=201)
def create_pack(
    payload: PackCreate,
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_platform_admin),
) -> object:
    try:
        return governance_service.create_pack(db, payload)
    except CommercialServiceError as exc:
        _raise(exc)


@catalog_router.get("/{pack_code}/versions", response_model=list[PackVersionRead])
def versions(
    pack_code: str,
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_platform_admin),
) -> object:
    try:
        return governance_service.versions(db, pack_code)
    except CommercialServiceError as exc:
        _raise(exc)


@catalog_router.post("/{pack_code}/versions", response_model=PackVersionRead, status_code=201)
def create_version(
    pack_code: str,
    payload: PackVersionCreate,
    db: Session = Depends(get_db),
    actor: AuthenticatedUser = Depends(require_platform_admin),
) -> object:
    try:
        return governance_service.create_version(db, pack_code, payload, actor.user_id)
    except CommercialServiceError as exc:
        _raise(exc)


@catalog_router.get("/versions/{version_id}/components", response_model=list[PackComponentRead])
def version_components(
    version_id: UUID,
    component_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_platform_admin),
) -> object:
    return governance_service.components(db, version_id, component_type)


@catalog_router.put("/versions/{version_id}/components", response_model=PackComponentRead)
def put_version_component(
    version_id: UUID,
    payload: PackComponentWrite,
    db: Session = Depends(get_db),
    actor: AuthenticatedUser = Depends(require_platform_admin),
) -> object:
    try:
        return governance_service.put_component(db, version_id, payload, actor.user_id)
    except CommercialServiceError as exc:
        _raise(exc)


@catalog_router.post("/versions/{version_id}/validate", response_model=PackVersionRead)
def validate_version(
    version_id: UUID,
    payload: PackTransition,
    db: Session = Depends(get_db),
    actor: AuthenticatedUser = Depends(require_platform_admin),
) -> object:
    try:
        return governance_service.validate(db, version_id, actor.user_id, payload.reason)
    except CommercialServiceError as exc:
        _raise(exc)


@catalog_router.post("/versions/{version_id}/{target}", response_model=PackVersionRead)
def transition_version(
    version_id: UUID,
    target: str,
    payload: PackTransition,
    db: Session = Depends(get_db),
    actor: AuthenticatedUser = Depends(require_platform_admin),
) -> object:
    try:
        return governance_service.transition(db, version_id, target, actor.user_id, payload.reason)
    except CommercialServiceError as exc:
        _raise(exc)


@tenant_router.get("", response_model=list[PackAssignmentRead])
def assignments(
    organization_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*COMMERCIAL_READ_ROLES)),
) -> object:
    return tenant_industry_pack_service.assignments(db, organization_id)


@tenant_router.post("", response_model=PackAssignmentRead, status_code=201)
def assign(
    organization_id: UUID,
    payload: PackAssignmentRequest,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*COMMERCIAL_ADMIN_ROLES)),
) -> object:
    try:
        return tenant_industry_pack_service.assign(
            db, organization_id, payload, access.user.user_id
        )
    except CommercialServiceError as exc:
        _raise(exc)


@tenant_router.post("/{assignment_id}/status/{status}", response_model=PackAssignmentRead)
def assignment_status(
    organization_id: UUID,
    assignment_id: UUID,
    status: str,
    payload: PackTransition,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*COMMERCIAL_ADMIN_ROLES)),
) -> object:
    try:
        return tenant_industry_pack_service.set_status(
            db,
            organization_id,
            assignment_id,
            status,
            access.user.user_id,
            payload.reason,
        )
    except CommercialServiceError as exc:
        _raise(exc)


@tenant_router.post(
    "/{assignment_id}/executions", response_model=PackExecutionRead, status_code=201
)
def execute(
    organization_id: UUID,
    assignment_id: UUID,
    payload: PackExecutionCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*COMMERCIAL_ADMIN_ROLES)),
) -> object:
    try:
        return tenant_industry_pack_service.execute(
            db, organization_id, assignment_id, payload, access.user.user_id
        )
    except CommercialServiceError as exc:
        _raise(exc)
