from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.authorization import OrganizationAccess, require_organization_roles
from app.auth.identity import AuthenticatedUser, get_current_user
from app.auth.permissions import ORGANIZATION_READ_ROLES
from app.db.session import get_db
from app.models.entities import Organization
from app.schemas.access import (
    AccessContextRead,
    AccessSummaryRead,
    CurrentIdentityRead,
    OrganizationSummary,
)
from app.schemas.contracts import OrganizationCreate
from app.services.access_context_service import (
    AccessContextServiceError,
    OrganizationProvisioningError,
    create_organization_with_owner,
    get_access_context,
    get_access_summary,
    get_current_identity,
)

organization_router = APIRouter(prefix="/api/v1/organizations")
me_router = APIRouter(prefix="/api/v1/me")


def _raise(exc: AccessContextServiceError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status, detail={"code": exc.code, "message": str(exc)}
    ) from exc


@me_router.post("/organizations", response_model=OrganizationSummary, status_code=201)
def create_my_organization(
    payload: OrganizationCreate,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> Organization:
    """Self-service organization creation: the caller becomes the org's
    first active organization_admin. Distinct from the pre-existing
    platform-admin-only POST /api/v1/organizations in app/api/routes.py,
    which provisions an organization without granting any membership."""
    try:
        return create_organization_with_owner(db, payload, current_user.user_id)
    except OrganizationProvisioningError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "organization_conflict", "message": str(exc)},
        ) from exc


@organization_router.get("/{organization_id}/access-summary", response_model=AccessSummaryRead)
def read_access_summary(
    organization_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*ORGANIZATION_READ_ROLES)),
) -> object:
    try:
        return get_access_summary(db, organization_id)
    except AccessContextServiceError as exc:
        _raise(exc)


@me_router.get("", response_model=CurrentIdentityRead)
def read_current_identity(
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> object:
    return get_current_identity(db, current_user)


@me_router.get("/context", response_model=AccessContextRead)
def read_access_context(
    organization_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> object:
    return get_access_context(db, current_user, organization_id)
