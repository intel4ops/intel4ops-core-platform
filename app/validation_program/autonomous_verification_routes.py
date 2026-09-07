from __future__ import annotations

from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.authorization import OrganizationAccess, require_organization_roles
from app.auth.permissions import ORGANIZATION_ADMIN_ROLES
from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.autonomous_verification_retest import (
    VerificationRetestComplete,
    VerificationRetestStart,
)
from app.storage.local_storage import LocalFileStorage
from app.validation_program.autonomous_verification_retest import (
    AutonomousVerificationRetestError,
    AutonomousVerificationRetestService,
)

router = APIRouter(prefix="/api/v1/organizations/{organization_id}/simulation-controller")


def _raise(exc: Exception) -> NoReturn:
    raise HTTPException(
        status_code=getattr(exc, "status", 400),
        detail={
            "code": getattr(exc, "code", "verification_retest_error"),
            "message": str(exc),
        },
    ) from exc


def _service() -> AutonomousVerificationRetestService:
    settings = get_settings()
    return AutonomousVerificationRetestService(LocalFileStorage(settings.storage_root))


@router.post("/codex-jobs/{job_id}/verification-retest/start")
def start_verification_retest(
    organization_id: UUID,
    job_id: UUID,
    payload: VerificationRetestStart,
    db: Session = Depends(get_db),
    _access: OrganizationAccess = Depends(require_organization_roles(*ORGANIZATION_ADMIN_ROLES)),
) -> dict[str, object]:
    try:
        lease = _service().start(db, organization_id, job_id, payload.worker_id)
    except AutonomousVerificationRetestError as exc:
        _raise(exc)
    return {
        "batch_id": lease.batch_id,
        "implementation_job_id": lease.job_id,
        "verification_lease_id": lease.lease_id,
        "worker_id": lease.worker_id,
        "manifest_ref": lease.manifest_ref,
        "automatic_merge_allowed": False,
        "automatic_deploy_allowed": False,
    }


@router.post("/codex-jobs/{job_id}/verification-retest/complete")
def complete_verification_retest(
    organization_id: UUID,
    job_id: UUID,
    payload: VerificationRetestComplete,
    db: Session = Depends(get_db),
    _access: OrganizationAccess = Depends(require_organization_roles(*ORGANIZATION_ADMIN_ROLES)),
) -> dict[str, object]:
    try:
        decision = _service().complete(db, organization_id, job_id, payload)
    except AutonomousVerificationRetestError as exc:
        _raise(exc)
    return {
        "batch_id": decision.batch_id,
        "implementation_job_id": decision.job_id,
        "decision": decision.decision,
        "verification_ref": decision.verification_ref,
        "owner_review_required": decision.owner_review_required,
        "automatic_merge_performed": False,
        "automatic_deploy_performed": False,
    }
