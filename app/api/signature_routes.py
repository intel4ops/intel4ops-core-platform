from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.authorization import (
    OrganizationAccess,
    require_organization_roles,
    require_platform_admin,
)
from app.auth.commercial import require_registered_application_client
from app.auth.identity import AuthenticatedUser
from app.auth.permissions import (
    SIGNATURE_ADMIN_ROLES,
    SIGNATURE_EXECUTION_ROLES,
    SIGNATURE_READ_ROLES,
)
from app.db.session import get_db
from app.schemas.signatures import (
    FeatureRead,
    FeatureVersionRead,
    SignatureDeploymentCreate,
    SignatureDeploymentRead,
    SignatureExecutionCreate,
    SignatureExecutionRead,
    SignatureRead,
    SignatureTransition,
    SignatureVersionRead,
)
from app.services.signature_service import (
    SignatureServiceError,
    signature_catalog_service,
    tenant_signature_service,
)

catalog_router = APIRouter(
    prefix="/api/v1/operational-intelligence",
    tags=["operational-signatures"],
    dependencies=[Depends(require_registered_application_client)],
)
tenant_router = APIRouter(
    prefix="/api/v1/organizations/{organization_id}/operational-signatures",
    tags=["operational-signatures"],
    dependencies=[Depends(require_registered_application_client)],
)


def _raise(exc: SignatureServiceError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status,
        detail={"code": exc.code, "message": str(exc)},
    ) from exc


@catalog_router.get("/features", response_model=list[FeatureRead])
def features(
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_platform_admin),
) -> object:
    return signature_catalog_service.features(db)


@catalog_router.get(
    "/features/{feature_id}/versions",
    response_model=list[FeatureVersionRead],
)
def feature_versions(
    feature_id: UUID,
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_platform_admin),
) -> object:
    return signature_catalog_service.feature_versions(db, feature_id)


@catalog_router.get("/signatures", response_model=list[SignatureRead])
def signatures(
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_platform_admin),
) -> object:
    return signature_catalog_service.signatures(db)


@catalog_router.get(
    "/signatures/{signature_id}/versions",
    response_model=list[SignatureVersionRead],
)
def signature_versions(
    signature_id: UUID,
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_platform_admin),
) -> object:
    return signature_catalog_service.versions(db, signature_id)


@catalog_router.post("/signatures/{signature_id}/transition", response_model=SignatureRead)
def transition(
    signature_id: UUID,
    payload: SignatureTransition,
    db: Session = Depends(get_db),
    actor: AuthenticatedUser = Depends(require_platform_admin),
) -> object:
    try:
        return signature_catalog_service.transition(
            db,
            signature_id,
            payload,
            actor.user_id,
            "platform_admin",
        )
    except SignatureServiceError as exc:
        _raise(exc)


@tenant_router.get("/deployments", response_model=list[SignatureDeploymentRead])
def deployments(
    organization_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*SIGNATURE_READ_ROLES)),
) -> object:
    return tenant_signature_service.deployments(db, organization_id)


@tenant_router.post(
    "/deployments",
    response_model=SignatureDeploymentRead,
    status_code=201,
)
def deploy(
    organization_id: UUID,
    payload: SignatureDeploymentCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*SIGNATURE_ADMIN_ROLES)),
) -> object:
    try:
        return tenant_signature_service.deploy(
            db,
            organization_id,
            payload,
            access.user.user_id,
        )
    except SignatureServiceError as exc:
        _raise(exc)


@tenant_router.post(
    "/deployments/{deployment_id}/executions",
    response_model=SignatureExecutionRead,
    status_code=201,
)
def execute(
    organization_id: UUID,
    deployment_id: UUID,
    payload: SignatureExecutionCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*SIGNATURE_EXECUTION_ROLES)),
) -> object:
    try:
        return tenant_signature_service.execute(
            db,
            organization_id,
            deployment_id,
            payload,
            access.user.user_id,
        )
    except SignatureServiceError as exc:
        _raise(exc)


@tenant_router.get(
    "/deployments/{deployment_id}/executions",
    response_model=list[SignatureExecutionRead],
)
def executions(
    organization_id: UUID,
    deployment_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*SIGNATURE_READ_ROLES)),
) -> object:
    return tenant_signature_service.executions(db, organization_id, deployment_id)
