from __future__ import annotations

from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.authorization import OrganizationAccess, require_organization_roles
from app.auth.permissions import ORGANIZATION_ADMIN_ROLES
from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.verified_release_authorization import VerifiedReleaseAuthorizationRequest
from app.storage.local_storage import LocalFileStorage
from app.validation_program.verified_release_authorization import (
    VerifiedReleaseAuthorizationError,
    VerifiedReleaseAuthorizationService,
)

router = APIRouter(prefix="/api/v1/organizations/{organization_id}/simulation-controller")


def _raise(exc: Exception) -> NoReturn:
    raise HTTPException(
        status_code=getattr(exc, "status", 400),
        detail={
            "code": getattr(exc, "code", "verified_release_authorization_error"),
            "message": str(exc),
        },
    ) from exc


def _service() -> VerifiedReleaseAuthorizationService:
    settings = get_settings()
    return VerifiedReleaseAuthorizationService(LocalFileStorage(settings.storage_root))


@router.post("/codex-jobs/{job_id}/release-authorization")
def authorize_verified_release(
    organization_id: UUID,
    job_id: UUID,
    payload: VerifiedReleaseAuthorizationRequest,
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
    except VerifiedReleaseAuthorizationError as exc:
        _raise(exc)
    return {
        "batch_id": decision.batch_id,
        "implementation_job_id": decision.job_id,
        "decision": decision.decision,
        "authorization_ref": decision.authorization_ref,
        "merge_allowed": decision.merge_allowed,
        "deploy_allowed": decision.deploy_allowed,
        "automatic_merge_performed": False,
        "automatic_deploy_performed": False,
    }
