from __future__ import annotations

from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.authorization import OrganizationAccess, require_organization_roles
from app.auth.permissions import ORGANIZATION_ADMIN_ROLES
from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.governed_merge_release_promotion import GovernedMergeComplete, GovernedMergeStart
from app.storage.local_storage import LocalFileStorage
from app.validation_program.governed_merge_release_promotion import (
    GovernedMergeReleasePromotionError,
    GovernedMergeReleasePromotionService,
)

router = APIRouter(prefix="/api/v1/organizations/{organization_id}/simulation-controller")


def _raise(exc: Exception) -> NoReturn:
    raise HTTPException(
        status_code=getattr(exc, "status", 400),
        detail={"code": getattr(exc, "code", "governed_merge_error"), "message": str(exc)},
    ) from exc


def _service() -> GovernedMergeReleasePromotionService:
    settings = get_settings()
    return GovernedMergeReleasePromotionService(LocalFileStorage(settings.storage_root))


@router.post("/codex-jobs/{job_id}/governed-merge/start")
def start_governed_merge(
    organization_id: UUID,
    job_id: UUID,
    payload: GovernedMergeStart,
    db: Session = Depends(get_db),
    _access: OrganizationAccess = Depends(require_organization_roles(*ORGANIZATION_ADMIN_ROLES)),
) -> dict[str, object]:
    try:
        lease = _service().start(db, organization_id, job_id, payload.worker_id)
    except GovernedMergeReleasePromotionError as exc:
        _raise(exc)
    return {
        "batch_id": lease.batch_id,
        "implementation_job_id": lease.job_id,
        "merge_lease_id": lease.lease_id,
        "worker_id": lease.worker_id,
        "manifest_ref": lease.manifest_ref,
        "deploy_allowed": False,
    }


@router.post("/codex-jobs/{job_id}/governed-merge/complete")
def complete_governed_merge(
    organization_id: UUID,
    job_id: UUID,
    payload: GovernedMergeComplete,
    db: Session = Depends(get_db),
    _access: OrganizationAccess = Depends(require_organization_roles(*ORGANIZATION_ADMIN_ROLES)),
) -> dict[str, object]:
    try:
        decision = _service().complete(db, organization_id, job_id, payload)
    except GovernedMergeReleasePromotionError as exc:
        _raise(exc)
    return {
        "batch_id": decision.batch_id,
        "implementation_job_id": decision.job_id,
        "decision": decision.decision,
        "promotion_ref": decision.promotion_ref,
        "deploy_allowed": decision.deploy_allowed,
        "automatic_deploy_performed": False,
    }
