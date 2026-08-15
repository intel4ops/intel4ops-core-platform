from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.commercial import require_commercial_entitlement
from app.auth.permissions import ACTION_READ_ROLES, RECOVERY_LEDGER_READ_ROLES
from app.db.session import get_db
from app.schemas.recovery_workspace import RecoveryWorkspaceRead
from app.services.decision_intelligence_service import DecisionIntelligenceServiceError
from app.services.recovery_workspace_service import recovery_workspace_service

router = APIRouter(
    prefix="/api/v1/organizations/{organization_id}/findings",
    tags=["recovery-workspace"],
    dependencies=[
        Depends(
            require_commercial_entitlement("recovery.action_orchestration", *ACTION_READ_ROLES)
        ),
        Depends(
            require_commercial_entitlement("recovery.value_ledger", *RECOVERY_LEDGER_READ_ROLES)
        ),
    ],
)


@router.get("/{finding_id}/recovery-workspace", response_model=RecoveryWorkspaceRead)
def get_recovery_workspace(
    organization_id: UUID,
    finding_id: UUID,
    db: Session = Depends(get_db),
) -> RecoveryWorkspaceRead:
    try:
        return recovery_workspace_service.get(db, organization_id, finding_id)
    except DecisionIntelligenceServiceError as exc:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=exc.status,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
