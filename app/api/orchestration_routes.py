from datetime import datetime
from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.authorization import (
    OrganizationAccess,
    require_organization_roles,
    require_platform_admin,
)
from app.auth.identity import AuthenticatedUser
from app.auth.permissions import (
    INTELLIGENCE_OPERATOR_ROLES,
    INTELLIGENCE_READ_ROLES,
    INTELLIGENCE_REQUEST_ROLES,
)
from app.db.session import get_db
from app.schemas.orchestration import (
    EngineRegistrationRead,
    OrchestrationAnalyticalLevel,
    OrchestrationCreate,
    OrchestrationDecisionRead,
    OrchestrationDetail,
    OrchestrationHistoryRead,
    OrchestrationPage,
    OrchestrationRead,
    OrchestrationStatusValue,
    OrchestrationStepRead,
)
from app.services.orchestration_service import OrchestrationError, orchestration_service

router = APIRouter(prefix="/api/v1/organizations/{organization_id}/intelligence")
engine_router = APIRouter(prefix="/api/v1/intelligence/engines")


def _raise(exc: OrchestrationError) -> NoReturn:
    raise HTTPException(
        status_code=exc.http_status,
        detail={"code": exc.code, "message": str(exc)},
    ) from exc


@router.post(
    "/orchestrations",
    response_model=OrchestrationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_orchestration(
    organization_id: UUID,
    payload: OrchestrationCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*INTELLIGENCE_REQUEST_ROLES)),
) -> object:
    try:
        return orchestration_service.orchestrate(db, organization_id, payload, access.user.user_id)
    except OrchestrationError as exc:
        _raise(exc)


@router.get("/orchestrations", response_model=OrchestrationPage)
def list_orchestrations(
    organization_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    status_filter: OrchestrationStatusValue | None = Query(default=None, alias="status"),
    analytical_level: OrchestrationAnalyticalLevel | None = None,
    definition_code: str | None = Query(default=None, max_length=100),
    engine_code: str | None = Query(default=None, max_length=100),
    requested_from: datetime | None = None,
    requested_to: datetime | None = None,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*INTELLIGENCE_READ_ROLES)),
) -> OrchestrationPage:
    items, total = orchestration_service.list_requests(
        db,
        organization_id,
        page=page,
        page_size=page_size,
        status=status_filter.value if status_filter else None,
        analytical_level=analytical_level.value if analytical_level else None,
        definition_code=definition_code,
        engine_code=engine_code,
        requested_from=requested_from,
        requested_to=requested_to,
    )
    return OrchestrationPage(items=items, page=page, page_size=page_size, total=total)


@router.get("/orchestrations/{orchestration_id}", response_model=OrchestrationDetail)
def get_orchestration(
    organization_id: UUID,
    orchestration_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*INTELLIGENCE_READ_ROLES)),
) -> OrchestrationDetail:
    try:
        request = orchestration_service.get(db, organization_id, orchestration_id)
        return OrchestrationDetail(
            **OrchestrationRead.model_validate(request).model_dump(),
            decisions=orchestration_service.decisions(db, organization_id, orchestration_id),
            steps=orchestration_service.steps(db, organization_id, orchestration_id),
            history=orchestration_service.history(db, organization_id, orchestration_id),
        )
    except OrchestrationError as exc:
        _raise(exc)


@router.get(
    "/orchestrations/{orchestration_id}/decisions",
    response_model=list[OrchestrationDecisionRead],
)
def get_orchestration_decisions(
    organization_id: UUID,
    orchestration_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*INTELLIGENCE_READ_ROLES)),
) -> object:
    try:
        return orchestration_service.decisions(db, organization_id, orchestration_id)
    except OrchestrationError as exc:
        _raise(exc)


@router.get(
    "/orchestrations/{orchestration_id}/steps",
    response_model=list[OrchestrationStepRead],
)
def get_orchestration_steps(
    organization_id: UUID,
    orchestration_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*INTELLIGENCE_OPERATOR_ROLES)),
) -> object:
    try:
        return orchestration_service.steps(db, organization_id, orchestration_id)
    except OrchestrationError as exc:
        _raise(exc)


@router.get(
    "/orchestrations/{orchestration_id}/history",
    response_model=list[OrchestrationHistoryRead],
)
def get_orchestration_history(
    organization_id: UUID,
    orchestration_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*INTELLIGENCE_OPERATOR_ROLES)),
) -> object:
    try:
        return orchestration_service.history(db, organization_id, orchestration_id)
    except OrchestrationError as exc:
        _raise(exc)


@engine_router.get("", response_model=list[EngineRegistrationRead])
def list_engines(
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_platform_admin),
) -> object:
    return orchestration_service.engines_list(db)


@engine_router.get("/{engine_code}", response_model=EngineRegistrationRead)
def get_engine(
    engine_code: str,
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_platform_admin),
) -> object:
    try:
        return orchestration_service.engine(db, engine_code)
    except OrchestrationError as exc:
        _raise(exc)
