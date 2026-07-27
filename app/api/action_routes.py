from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.authorization import OrganizationAccess, require_organization_roles
from app.auth.commercial import require_commercial_entitlement
from app.auth.permissions import (
    ACTION_APPROVE_ROLES,
    ACTION_ASSIGN_ROLES,
    ACTION_CREATE_ROLES,
    ACTION_FEEDBACK_ROLES,
    ACTION_OUTCOME_ROLES,
    ACTION_PLAN_ROLES,
    ACTION_READ_ROLES,
    ACTION_TRANSITION_ROLES,
    ACTION_VERIFY_ROLES,
)
from app.db.session import get_db
from app.models.actions import ActionEvent
from app.schemas.actions import (
    ActionAssignmentCreate,
    ActionCreate,
    ActionDependencyCreate,
    ActionEvidenceCreate,
    ActionFeedbackCreate,
    ActionOutcomeCreate,
    ActionPage,
    ActionPlanStepCreate,
    ActionRead,
    ActionResourceCreate,
    ActionTransitionCreate,
)
from app.services.action_service import ActionServiceError, action_service

router = APIRouter(
    prefix="/api/v1/organizations/{organization_id}/actions",
    dependencies=[
        Depends(require_commercial_entitlement("recovery.action_orchestration", *ACTION_READ_ROLES))
    ],
)


def _role(access: OrganizationAccess) -> str:
    return access.membership.role if access.membership is not None else "platform_admin"


def _raise(exc: ActionServiceError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status, detail={"code": exc.code, "message": str(exc)}
    ) from exc


@router.post("", response_model=ActionRead, status_code=201)
@router.post("/from-reliability", response_model=ActionRead, status_code=201)
@router.post("/from-finding", response_model=ActionRead, status_code=201)
def create(
    organization_id: UUID,
    payload: ActionCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ACTION_CREATE_ROLES)),
) -> object:
    try:
        return action_service.create(db, organization_id, payload, access.user.user_id)
    except ActionServiceError as exc:
        _raise(exc)


@router.get("", response_model=ActionPage)
def list_actions(
    organization_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    status: str | None = None,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*ACTION_READ_ROLES)),
) -> ActionPage:
    rows, total = action_service.list(db, organization_id, page, page_size, status)
    return ActionPage(items=rows, page=page, page_size=page_size, total=total)


@router.get("/{action_id}", response_model=ActionRead)
def get(
    organization_id: UUID,
    action_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*ACTION_READ_ROLES)),
) -> object:
    try:
        return action_service.get(db, organization_id, action_id)
    except ActionServiceError as exc:
        _raise(exc)


@router.post("/{action_id}/transition", response_model=ActionRead)
@router.post("/{action_id}/submit-approval", response_model=ActionRead)
@router.post("/{action_id}/complete", response_model=ActionRead)
def transition(
    organization_id: UUID,
    action_id: UUID,
    payload: ActionTransitionCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ACTION_TRANSITION_ROLES)),
) -> object:
    try:
        return action_service.transition(
            db, organization_id, action_id, payload, access.user.user_id, _role(access)
        )
    except (ActionServiceError, ValueError) as exc:
        if isinstance(exc, ActionServiceError):
            _raise(exc)
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _transition_with_access(
    db: Session,
    organization_id: UUID,
    action_id: UUID,
    payload: ActionTransitionCreate,
    access: OrganizationAccess,
) -> object:
    try:
        return action_service.transition(
            db, organization_id, action_id, payload, access.user.user_id, _role(access)
        )
    except (ActionServiceError, ValueError) as exc:
        if isinstance(exc, ActionServiceError):
            _raise(exc)
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{action_id}/approve", response_model=ActionRead)
@router.post("/{action_id}/reject", response_model=ActionRead)
def approval_decision(
    organization_id: UUID,
    action_id: UUID,
    payload: ActionTransitionCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ACTION_APPROVE_ROLES)),
) -> object:
    return _transition_with_access(db, organization_id, action_id, payload, access)


@router.post("/{action_id}/verify", response_model=ActionRead)
@router.post("/{action_id}/reject-verification", response_model=ActionRead)
def verification_decision(
    organization_id: UUID,
    action_id: UUID,
    payload: ActionTransitionCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ACTION_VERIFY_ROLES)),
) -> object:
    return _transition_with_access(db, organization_id, action_id, payload, access)


@router.post("/{action_id}/assign", response_model=ActionRead)
def assign(
    organization_id: UUID,
    action_id: UUID,
    payload: ActionAssignmentCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ACTION_ASSIGN_ROLES)),
) -> object:
    try:
        return action_service.assign(
            db, organization_id, action_id, payload, access.user.user_id, _role(access)
        )
    except ActionServiceError as exc:
        _raise(exc)


@router.post("/{action_id}/plan", status_code=201)
def plan(
    organization_id: UUID,
    action_id: UUID,
    payload: ActionPlanStepCreate,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*ACTION_PLAN_ROLES)),
) -> object:
    try:
        return jsonable_encoder(
            action_service.add_plan_step(db, organization_id, action_id, payload)
        )
    except ActionServiceError as exc:
        _raise(exc)


@router.post("/{action_id}/dependencies", status_code=201)
def dependency(
    organization_id: UUID,
    action_id: UUID,
    payload: ActionDependencyCreate,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*ACTION_PLAN_ROLES)),
) -> object:
    try:
        return jsonable_encoder(
            action_service.add_dependency(db, organization_id, action_id, payload)
        )
    except ActionServiceError as exc:
        _raise(exc)


@router.post("/{action_id}/resources", status_code=201)
def resource(
    organization_id: UUID,
    action_id: UUID,
    payload: ActionResourceCreate,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*ACTION_PLAN_ROLES)),
) -> object:
    try:
        return jsonable_encoder(
            action_service.add_resource(db, organization_id, action_id, payload)
        )
    except ActionServiceError as exc:
        _raise(exc)


@router.post("/{action_id}/evidence", status_code=201)
def evidence(
    organization_id: UUID,
    action_id: UUID,
    payload: ActionEvidenceCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ACTION_VERIFY_ROLES)),
) -> object:
    try:
        return jsonable_encoder(
            action_service.add_evidence(
                db, organization_id, action_id, payload, access.user.user_id
            )
        )
    except ActionServiceError as exc:
        _raise(exc)


@router.post("/{action_id}/outcomes", status_code=201)
def outcome(
    organization_id: UUID,
    action_id: UUID,
    payload: ActionOutcomeCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ACTION_OUTCOME_ROLES)),
) -> object:
    try:
        return jsonable_encoder(
            action_service.record_outcome(
                db, organization_id, action_id, payload, access.user.user_id
            )
        )
    except ActionServiceError as exc:
        _raise(exc)


@router.post("/{action_id}/model-feedback", status_code=201)
def feedback(
    organization_id: UUID,
    action_id: UUID,
    payload: ActionFeedbackCreate,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*ACTION_FEEDBACK_ROLES)),
) -> object:
    try:
        return jsonable_encoder(action_service.feedback(db, organization_id, action_id, payload))
    except ActionServiceError as exc:
        _raise(exc)


@router.get("/{action_id}/history")
def history(
    organization_id: UUID,
    action_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*ACTION_READ_ROLES)),
) -> object:
    action_service.get(db, organization_id, action_id)
    return jsonable_encoder(
        list(
            db.scalars(
                select(ActionEvent)
                .where(
                    ActionEvent.organization_id == organization_id,
                    ActionEvent.action_id == action_id,
                )
                .order_by(ActionEvent.occurred_at, ActionEvent.id)
            )
        )
    )
