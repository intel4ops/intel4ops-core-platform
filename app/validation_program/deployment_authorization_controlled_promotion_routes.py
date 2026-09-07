from __future__ import annotations

from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.authorization import OrganizationAccess, require_organization_roles
from app.auth.permissions import ORGANIZATION_ADMIN_ROLES
from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.deployment_authorization_controlled_promotion import (
    ControlledPromotionComplete,
    ControlledPromotionStart,
    DeploymentAuthorizationRequest,
)
from app.storage.local_storage import LocalFileStorage
from app.validation_program.deployment_authorization_controlled_promotion import (
    DeploymentAuthorizationControlledPromotionError,
    DeploymentAuthorizationControlledPromotionService,
)

router = APIRouter(prefix="/api/v1/organizations/{organization_id}/simulation-controller")


def _raise(exc: Exception) -> NoReturn:
    raise HTTPException(
        status_code=getattr(exc, "status", 400),
        detail={
            "code": getattr(exc, "code", "deployment_authorization_error"),
            "message": str(exc),
        },
    ) from exc


def _service() -> DeploymentAuthorizationControlledPromotionService:
    settings = get_settings()
    return DeploymentAuthorizationControlledPromotionService(
        LocalFileStorage(settings.storage_root)
    )


@router.post("/codex-jobs/{job_id}/deployment-authorization")
def authorize_deployment(
    organization_id: UUID,
    job_id: UUID,
    payload: DeploymentAuthorizationRequest,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ORGANIZATION_ADMIN_ROLES)),
) -> dict[str, object]:
    try:
        decision = _service().authorize(
            db,
            organization_id,
            job_id,
            access.user.user_id,
            payload,
        )
    except DeploymentAuthorizationControlledPromotionError as exc:
        _raise(exc)
    return {
        "batch_id": decision.batch_id,
        "implementation_job_id": decision.job_id,
        "decision": decision.decision,
        "authorization_ref": decision.authorization_ref,
        "environment": decision.environment,
        "deploy_allowed": decision.deploy_allowed,
        "cross_environment_deploy_allowed": False,
    }


@router.post("/codex-jobs/{job_id}/controlled-promotion/start")
def start_controlled_promotion(
    organization_id: UUID,
    job_id: UUID,
    payload: ControlledPromotionStart,
    db: Session = Depends(get_db),
    _access: OrganizationAccess = Depends(require_organization_roles(*ORGANIZATION_ADMIN_ROLES)),
) -> dict[str, object]:
    try:
        lease = _service().start(
            db,
            organization_id,
            job_id,
            payload.environment,
            payload.expected_merge_commit_sha,
            payload.worker_id,
        )
    except DeploymentAuthorizationControlledPromotionError as exc:
        _raise(exc)
    return {
        "batch_id": lease.batch_id,
        "implementation_job_id": lease.job_id,
        "promotion_lease_id": lease.lease_id,
        "manifest_ref": lease.manifest_ref,
        "environment": lease.environment,
        "cross_environment_deploy_allowed": False,
    }


@router.post("/codex-jobs/{job_id}/controlled-promotion/complete")
def complete_controlled_promotion(
    organization_id: UUID,
    job_id: UUID,
    payload: ControlledPromotionComplete,
    db: Session = Depends(get_db),
    _access: OrganizationAccess = Depends(require_organization_roles(*ORGANIZATION_ADMIN_ROLES)),
) -> dict[str, object]:
    try:
        decision = _service().complete(db, organization_id, job_id, payload)
    except DeploymentAuthorizationControlledPromotionError as exc:
        _raise(exc)
    return {
        "batch_id": decision.batch_id,
        "implementation_job_id": decision.job_id,
        "decision": decision.decision,
        "result_ref": decision.result_ref,
        "environment": decision.environment,
        "cross_environment_promotion_performed": False,
    }
