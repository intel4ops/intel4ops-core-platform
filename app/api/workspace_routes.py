from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.authorization import OrganizationAccess, require_organization_roles
from app.auth.identity import AuthenticatedUser, get_current_user
from app.auth.permissions import ORGANIZATION_ADMIN_ROLES, ORGANIZATION_READ_ROLES
from app.db.session import get_db
from app.registries.challenge_registry import list_challenges as registry_challenges
from app.registries.industry_registry import list_industries as registry_industries
from app.registries.objective_registry import list_objectives as registry_objectives
from app.registries.system_registry import list_systems as registry_systems
from app.schemas.workspace import (
    ChallengeRead,
    IndustryRead,
    ObjectiveRead,
    OrganizationChallengeRead,
    OrganizationChallengesReplace,
    OrganizationObjectiveRead,
    OrganizationObjectivesReplace,
    OrganizationSystemRead,
    OrganizationSystemsReplace,
    SystemRead,
    TeamSummaryRead,
    WorkspaceSummaryRead,
)
from app.services.workspace_service import (
    WorkspaceServiceError,
    get_team_summary,
    get_workspace_summary,
    list_challenges,
    list_objectives,
    list_systems,
    replace_challenges,
    replace_objectives,
    replace_systems,
)

catalog_router = APIRouter(prefix="/api/v1", tags=["workspace"])
tenant_router = APIRouter(prefix="/api/v1/organizations/{organization_id}", tags=["workspace"])


def _raise(exc: WorkspaceServiceError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status, detail={"code": exc.code, "message": str(exc)}
    ) from exc


@catalog_router.get("/industries", response_model=list[IndustryRead])
def get_industries(_: AuthenticatedUser = Depends(get_current_user)) -> object:
    return registry_industries()


@catalog_router.get("/objectives", response_model=list[ObjectiveRead])
def get_objective_catalog(_: AuthenticatedUser = Depends(get_current_user)) -> object:
    return registry_objectives()


@catalog_router.get("/challenges", response_model=list[ChallengeRead])
def get_challenge_catalog(_: AuthenticatedUser = Depends(get_current_user)) -> object:
    return registry_challenges()


@catalog_router.get("/systems", response_model=list[SystemRead])
def get_system_catalog(_: AuthenticatedUser = Depends(get_current_user)) -> object:
    return registry_systems()


@tenant_router.get("/workspace-summary", response_model=WorkspaceSummaryRead)
def read_workspace_summary(
    organization_id: UUID,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ORGANIZATION_READ_ROLES)),
) -> object:
    try:
        return get_workspace_summary(db, organization_id, access.user.user_id)
    except WorkspaceServiceError as exc:
        _raise(exc)


@tenant_router.get("/team-summary", response_model=TeamSummaryRead)
def read_team_summary(
    organization_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*ORGANIZATION_READ_ROLES)),
) -> object:
    return get_team_summary(db, organization_id)


@tenant_router.get("/objectives", response_model=list[OrganizationObjectiveRead])
def read_objectives(
    organization_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*ORGANIZATION_READ_ROLES)),
) -> object:
    return list_objectives(db, organization_id)


@tenant_router.put("/objectives", response_model=list[OrganizationObjectiveRead])
def write_objectives(
    organization_id: UUID,
    payload: OrganizationObjectivesReplace,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ORGANIZATION_ADMIN_ROLES)),
) -> object:
    try:
        return replace_objectives(db, organization_id, payload.objective_codes, access.user.user_id)
    except WorkspaceServiceError as exc:
        _raise(exc)


@tenant_router.get("/challenges", response_model=list[OrganizationChallengeRead])
def read_challenges(
    organization_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*ORGANIZATION_READ_ROLES)),
) -> object:
    return list_challenges(db, organization_id)


@tenant_router.put("/challenges", response_model=list[OrganizationChallengeRead])
def write_challenges(
    organization_id: UUID,
    payload: OrganizationChallengesReplace,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ORGANIZATION_ADMIN_ROLES)),
) -> object:
    try:
        return replace_challenges(db, organization_id, payload.challenge_codes, access.user.user_id)
    except WorkspaceServiceError as exc:
        _raise(exc)


@tenant_router.get("/systems", response_model=list[OrganizationSystemRead])
def read_systems(
    organization_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*ORGANIZATION_READ_ROLES)),
) -> object:
    return list_systems(db, organization_id)


@tenant_router.put("/systems", response_model=list[OrganizationSystemRead])
def write_systems(
    organization_id: UUID,
    payload: OrganizationSystemsReplace,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ORGANIZATION_ADMIN_ROLES)),
) -> object:
    try:
        return replace_systems(db, organization_id, payload.systems, access.user.user_id)
    except WorkspaceServiceError as exc:
        _raise(exc)
