from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.authorization import OrganizationAccess
from app.auth.commercial import require_commercial_entitlement
from app.auth.permissions import (
    ACTION_READ_ROLES,
    FINDING_ADMIN_ROLES,
    FINDING_READ_ROLES,
    FINDING_REVIEW_ROLES,
    RECOVERY_LEDGER_READ_ROLES,
)
from app.db.session import get_db
from app.schemas.learning import (
    LearningCreate,
    LearningPage,
    LearningRead,
    LearningTransition,
    OperationalMemoryRead,
)
from app.services.learning_service import LearningServiceError, learning_service

router = APIRouter(prefix="/api/v1/organizations/{organization_id}", tags=["operational-learning"])


def _error(exc: LearningServiceError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status, detail={"code": exc.code, "message": str(exc)}
    ) from exc


def _role(access: OrganizationAccess) -> str:
    return "platform_admin" if access.membership is None else str(access.membership.role)


@router.get(
    "/findings/{finding_id}/operational-memory",
    response_model=OperationalMemoryRead,
)
def get_operational_memory(
    organization_id: UUID,
    finding_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(
        require_commercial_entitlement("intelligence.findings", *FINDING_READ_ROLES)
    ),
    __: OrganizationAccess = Depends(
        require_commercial_entitlement("recovery.action_orchestration", *ACTION_READ_ROLES)
    ),
    ___: OrganizationAccess = Depends(
        require_commercial_entitlement("recovery.value_ledger", *RECOVERY_LEDGER_READ_ROLES)
    ),
) -> OperationalMemoryRead:
    try:
        return learning_service.operational_memory(db, organization_id, finding_id)
    except LearningServiceError as exc:
        _error(exc)


@router.get("/learning", response_model=LearningPage)
def list_learning(
    organization_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    status: str | None = None,
    provenance: str | None = None,
    learning_type: str | None = None,
    source_finding_id: UUID | None = None,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(
        require_commercial_entitlement("intelligence.findings", *FINDING_READ_ROLES)
    ),
) -> LearningPage:
    return learning_service.list_learning(
        db,
        organization_id,
        page=page,
        page_size=page_size,
        status=status,
        provenance=provenance,
        learning_type=learning_type,
        source_finding_id=source_finding_id,
    )


@router.get("/learning/{learning_id}", response_model=LearningRead)
def get_learning(
    organization_id: UUID,
    learning_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(
        require_commercial_entitlement("intelligence.findings", *FINDING_READ_ROLES)
    ),
) -> LearningRead:
    try:
        return learning_service.get(db, organization_id, learning_id)
    except LearningServiceError as exc:
        _error(exc)


@router.post("/learning", response_model=LearningRead, status_code=201)
def create_learning(
    organization_id: UUID,
    payload: LearningCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(
        require_commercial_entitlement("intelligence.findings", *FINDING_REVIEW_ROLES)
    ),
) -> LearningRead:
    try:
        return learning_service.create(
            db, organization_id, payload, access.user.user_id, _role(access)
        )
    except LearningServiceError as exc:
        _error(exc)


def _transition(
    db: Session,
    organization_id: UUID,
    learning_id: UUID,
    payload: LearningTransition,
    expected: str,
    access: OrganizationAccess,
) -> LearningRead:
    if payload.transition != expected:
        _error(
            LearningServiceError("TRANSITION_COMMAND_MISMATCH", "Transition does not match route")
        )
    try:
        return learning_service.transition(
            db, organization_id, learning_id, payload, access.user.user_id, _role(access)
        )
    except LearningServiceError as exc:
        _error(exc)


@router.post("/learning/{learning_id}/review", response_model=LearningRead)
def review_learning(
    organization_id: UUID,
    learning_id: UUID,
    payload: LearningTransition,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(
        require_commercial_entitlement("intelligence.findings", *FINDING_REVIEW_ROLES)
    ),
) -> LearningRead:
    return _transition(db, organization_id, learning_id, payload, "review", access)


@router.post("/learning/{learning_id}/{command}", response_model=LearningRead)
def govern_learning(
    organization_id: UUID,
    learning_id: UUID,
    command: str,
    payload: LearningTransition,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(
        require_commercial_entitlement("intelligence.findings", *FINDING_ADMIN_ROLES)
    ),
) -> LearningRead:
    if command not in {"approve", "reject", "retire"}:
        raise HTTPException(
            status_code=404,
            detail={"code": "COMMAND_NOT_FOUND", "message": "Learning command not found"},
        )
    return _transition(db, organization_id, learning_id, payload, command, access)
