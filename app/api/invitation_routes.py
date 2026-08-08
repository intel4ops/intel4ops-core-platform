from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.authorization import OrganizationAccess, require_organization_roles
from app.auth.identity import AuthenticatedUser, get_current_user
from app.auth.permissions import ORGANIZATION_ADMIN_ROLES, ORGANIZATION_READ_ROLES
from app.db.session import get_db
from app.models.access import InvitationStatus
from app.models.entities import OrganizationMembership
from app.schemas.access import (
    InvitationAccept,
    InvitationCreate,
    InvitationCreateResult,
    InvitationRead,
)
from app.schemas.memberships import MembershipRead
from app.services.invitation_service import InvitationServiceError, invitation_service

router = APIRouter(prefix="/api/v1/organizations/{organization_id}/invitations")
accept_router = APIRouter(prefix="/api/v1/invitations")


def _raise(exc: InvitationServiceError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status, detail={"code": exc.code, "message": str(exc)}
    ) from exc


@router.post("", response_model=InvitationCreateResult, status_code=201)
def create_invitation(
    organization_id: UUID,
    payload: InvitationCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ORGANIZATION_ADMIN_ROLES)),
) -> object:
    try:
        invitation, token = invitation_service.create(
            db, organization_id, payload, invited_by_user_id=access.user.user_id
        )
    except InvitationServiceError as exc:
        _raise(exc)
    return InvitationCreateResult(invitation=invitation, token=token)


@router.get("", response_model=list[InvitationRead])
def list_invitations(
    organization_id: UUID,
    status: InvitationStatus | None = Query(default=None),
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*ORGANIZATION_READ_ROLES)),
) -> object:
    return invitation_service.list(db, organization_id, status=status)


@router.post("/{invitation_id}/revoke", response_model=InvitationRead)
def revoke_invitation(
    organization_id: UUID,
    invitation_id: UUID,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ORGANIZATION_ADMIN_ROLES)),
) -> object:
    try:
        return invitation_service.revoke(db, organization_id, invitation_id, access.user.user_id)
    except InvitationServiceError as exc:
        _raise(exc)


@accept_router.post("/accept", response_model=MembershipRead)
def accept_invitation(
    payload: InvitationAccept,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> OrganizationMembership:
    try:
        return invitation_service.accept(db, payload.token, current_user.user_id)
    except InvitationServiceError as exc:
        _raise(exc)
