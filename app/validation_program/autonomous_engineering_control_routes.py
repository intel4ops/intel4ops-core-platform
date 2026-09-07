from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from app.auth.authorization import OrganizationAccess, require_organization_roles
from app.auth.permissions import ORGANIZATION_ADMIN_ROLES
from app.core.config import get_settings
from app.schemas.autonomous_engineering_control import AutonomousEngineeringPolicyRequest
from app.storage.local_storage import LocalFileStorage
from app.validation_program.autonomous_engineering_control import (
    AutonomousEngineeringControlService,
)

router = APIRouter(prefix="/api/v1/organizations/{organization_id}/simulation-controller")


def _service() -> AutonomousEngineeringControlService:
    settings = get_settings()
    return AutonomousEngineeringControlService(LocalFileStorage(settings.storage_root))


@router.post("/autonomy/evaluate")
def evaluate_autonomy_policy(
    organization_id: UUID,
    payload: AutonomousEngineeringPolicyRequest,
    _access: OrganizationAccess = Depends(require_organization_roles(*ORGANIZATION_ADMIN_ROLES)),
) -> dict[str, object]:
    decision = _service().evaluate(organization_id, payload)
    return {
        "decision_id": decision.decision_id,
        "decision": decision.decision,
        "owner_required": decision.owner_required,
        "auto_execute_allowed": decision.auto_execute_allowed,
        "auto_merge_allowed": decision.auto_merge_allowed,
        "auto_deploy_staging_allowed": decision.auto_deploy_staging_allowed,
        "production_deploy_allowed": decision.production_deploy_allowed,
        "reason": decision.reason,
        "artifact_ref": decision.artifact_ref,
    }
