from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.commercial import require_commercial_entitlement
from app.auth.permissions import ORGANIZATION_READ_ROLES
from app.db.session import get_db
from app.schemas.executive_command import (
    AttentionItem,
    CurrencyExecutiveSummary,
    ExecutiveSummary,
    RecoveryPortfolio,
    TrendPoint,
)
from app.services.executive_command_service import executive_command_service

router = APIRouter(
    prefix="/api/v1/organizations/{organization_id}/command",
    tags=["Executive Command"],
    dependencies=[
        Depends(require_commercial_entitlement(key, *ORGANIZATION_READ_ROLES))
        for key in (
            "product.I4O-COMMAND",
            "command.executive_kpis",
            "commercial.api_access",
        )
    ],
)


@router.get("/executive-summary", response_model=ExecutiveSummary)
def summary(
    organization_id: UUID,
    period_start: datetime = Query(),
    period_end: datetime = Query(),
    db: Session = Depends(get_db),
) -> object:
    return executive_command_service.summary(db, organization_id, period_start, period_end)


@router.get("/attention", response_model=list[AttentionItem])
def attention(
    organization_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> object:
    return executive_command_service.attention(db, organization_id, limit)


@router.get("/recovery-portfolio", response_model=RecoveryPortfolio)
def recovery_portfolio(
    organization_id: UUID,
    at: datetime = Query(),
    db: Session = Depends(get_db),
) -> object:
    return executive_command_service.recovery_portfolio(db, organization_id, at)


@router.get("/value-portfolio", response_model=list[CurrencyExecutiveSummary])
def value_portfolio(
    organization_id: UUID,
    period_start: datetime = Query(),
    period_end: datetime = Query(),
    db: Session = Depends(get_db),
) -> object:
    return executive_command_service.summary(
        db, organization_id, period_start, period_end
    ).currencies


@router.get("/trends", response_model=list[TrendPoint])
def trends(
    organization_id: UUID,
    period_start: datetime = Query(),
    period_end: datetime = Query(),
    db: Session = Depends(get_db),
) -> object:
    return executive_command_service.trends(db, organization_id, period_start, period_end)
