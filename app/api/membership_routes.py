from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.authorization import OrganizationAccess, require_organization_roles
from app.auth.permissions import ORGANIZATION_ADMIN_ROLES, ORGANIZATION_READ_ROLES
from app.db.session import get_db
from app.models.entities import MembershipRole, MembershipStatus, OrganizationMembership
from app.schemas.memberships import MembershipCreate, MembershipRead, MembershipRoleUpdate
from app.services.membership_service import (
    DuplicateMembershipError,
    LastActiveOrganizationAdminError,
    MembershipNotFoundError,
    MembershipOrganizationNotFoundError,
    membership_service,
)

router = APIRouter(prefix="/api/v1/organizations/{organization_id}/members")


@router.post("", response_model=MembershipRead, status_code=status.HTTP_201_CREATED)
def create_membership(
    organization_id: UUID,
    payload: MembershipCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ORGANIZATION_ADMIN_ROLES)),
) -> OrganizationMembership:
    try:
        return membership_service.create(
            db,
            organization_id,
            payload,
            invited_by_user_id=access.user.user_id,
        )
    except MembershipOrganizationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DuplicateMembershipError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("", response_model=list[MembershipRead])
def list_memberships(
    organization_id: UUID,
    role: MembershipRole | None = None,
    membership_status: MembershipStatus | None = Query(default=None, alias="status"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*ORGANIZATION_READ_ROLES)),
) -> list[OrganizationMembership]:
    return membership_service.list(
        db,
        organization_id,
        role=role,
        status=membership_status,
        offset=offset,
        limit=limit,
    )


@router.get("/{membership_id}", response_model=MembershipRead)
def get_membership(
    organization_id: UUID,
    membership_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*ORGANIZATION_READ_ROLES)),
) -> OrganizationMembership:
    try:
        return membership_service.get(db, organization_id, membership_id)
    except MembershipNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{membership_id}/role", response_model=MembershipRead)
def update_membership_role(
    organization_id: UUID,
    membership_id: UUID,
    payload: MembershipRoleUpdate,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*ORGANIZATION_ADMIN_ROLES)),
) -> OrganizationMembership:
    try:
        return membership_service.update_role(db, organization_id, membership_id, payload.role)
    except MembershipNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LastActiveOrganizationAdminError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{membership_id}/activate", response_model=MembershipRead)
def activate_membership(
    organization_id: UUID,
    membership_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*ORGANIZATION_ADMIN_ROLES)),
) -> OrganizationMembership:
    try:
        return membership_service.activate(db, organization_id, membership_id)
    except MembershipNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{membership_id}/suspend", response_model=MembershipRead)
def suspend_membership(
    organization_id: UUID,
    membership_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*ORGANIZATION_ADMIN_ROLES)),
) -> OrganizationMembership:
    try:
        return membership_service.suspend(db, organization_id, membership_id)
    except MembershipNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LastActiveOrganizationAdminError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{membership_id}/revoke", response_model=MembershipRead)
def revoke_membership(
    organization_id: UUID,
    membership_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*ORGANIZATION_ADMIN_ROLES)),
) -> OrganizationMembership:
    try:
        return membership_service.revoke(db, organization_id, membership_id)
    except MembershipNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LastActiveOrganizationAdminError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
