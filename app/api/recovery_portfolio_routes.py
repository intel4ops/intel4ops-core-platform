from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.commercial import require_commercial_entitlement
from app.auth.permissions import ACTION_READ_ROLES, RECOVERY_LEDGER_READ_ROLES
from app.db.session import get_db
from app.schemas.recovery_portfolio import RecoveryPortfolioRead
from app.services.recovery_portfolio_service import recovery_portfolio_service

router = APIRouter(
    prefix="/api/v1/organizations/{organization_id}/recovery",
    tags=["recovery-portfolio"],
    dependencies=[
        Depends(
            require_commercial_entitlement("recovery.action_orchestration", *ACTION_READ_ROLES)
        ),
        Depends(
            require_commercial_entitlement("recovery.value_ledger", *RECOVERY_LEDGER_READ_ROLES)
        ),
    ],
)


@router.get("/portfolio", response_model=RecoveryPortfolioRead)
def get_recovery_portfolio(
    organization_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    owner_user_id: UUID | None = None,
    owner_role: str | None = None,
    currency: str | None = Query(default=None, pattern=r"^[A-Z]{3}$"),
    overdue_only: bool = False,
    verification_status: str | None = None,
    finding_id: UUID | None = None,
    action_id: UUID | None = None,
    recovery_case_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> RecoveryPortfolioRead:
    return recovery_portfolio_service.get(
        db,
        organization_id,
        page=page,
        page_size=page_size,
        owner_user_id=owner_user_id,
        owner_role=owner_role,
        currency=currency,
        overdue_only=overdue_only,
        verification_status=verification_status,
        finding_id=finding_id,
        action_id=action_id,
        recovery_case_id=recovery_case_id,
    )
