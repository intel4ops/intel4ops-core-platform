from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.identity import AuthenticatedUser, get_current_user
from app.auth.permissions import (
    OIKB_AUTHOR_ROLES,
    OIKB_GOVERNANCE_ROLES,
    OIKB_READ_ROLES,
    OIKB_VALIDATION_ROLES,
)
from app.db.session import get_db
from app.models.entities import MembershipRole
from app.models.oikb import OIKBChangeLog
from app.schemas.oikb import (
    DefinitionCreate,
    DefinitionPage,
    DefinitionRead,
    DefinitionUpdate,
    DefinitionVersionCreate,
    ExecutionPackage,
    GovernanceAction,
    LifecycleStatus,
    ResolutionRead,
    ResolveRequest,
    SourceCreate,
    SourceLinkCreate,
    ValidationCaseCreate,
    VersionRead,
)
from app.services.membership_service import MembershipAuthorizationError, membership_service
from app.services.oikb_service import (
    OIKBError,
    definition_registry_service,
    execution_package_export_service,
    governance_service,
    knowledge_resolution_service,
    knowledge_validation_service,
    source_citation_service,
)

router = APIRouter(prefix="/api/v1/oikb", tags=["OIKB"])


def _authorize(
    db: Session,
    user: AuthenticatedUser,
    organization_id: UUID | None,
    roles: tuple[MembershipRole, ...],
) -> None:
    if user.is_platform_admin:
        return
    if organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "OIKB_ACCESS_DENIED", "message": "Platform administration required"},
        )
    try:
        membership_service.require_roles(
            db,
            organization_id=organization_id,
            user_id=user.user_id,
            allowed_roles=set(roles),
        )
    except MembershipAuthorizationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "OIKB_ACCESS_DENIED", "message": "Organization access denied"},
        ) from exc


def _raise(exc: OIKBError) -> NoReturn:
    raise HTTPException(
        status_code=exc.http_status,
        detail={"code": exc.code, "message": str(exc)},
    ) from exc


@router.post("/definitions", response_model=DefinitionRead, status_code=201)
def create_definition(
    payload: DefinitionCreate,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> object:
    _authorize(db, user, payload.owner_organization_id, OIKB_AUTHOR_ROLES)
    try:
        return definition_registry_service.create(db, payload, user.user_id)
    except OIKBError as exc:
        _raise(exc)


@router.get("/definitions", response_model=DefinitionPage)
def list_definitions(
    organization_id: UUID | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> DefinitionPage:
    _authorize(db, user, organization_id, OIKB_READ_ROLES)
    items, total = definition_registry_service.list_definitions(
        db, organization_id, page=page, page_size=page_size
    )
    return DefinitionPage(
        items=[DefinitionRead.model_validate(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/definitions/{definition_id}", response_model=DefinitionRead)
def get_definition(
    definition_id: UUID,
    organization_id: UUID | None = None,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> object:
    _authorize(db, user, organization_id, OIKB_READ_ROLES)
    try:
        return definition_registry_service.get(db, definition_id, organization_id)
    except OIKBError as exc:
        _raise(exc)


@router.patch("/definitions/{definition_id}", response_model=DefinitionRead)
def update_definition(
    definition_id: UUID,
    payload: DefinitionUpdate,
    organization_id: UUID | None = None,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> object:
    _authorize(db, user, organization_id, OIKB_AUTHOR_ROLES)
    try:
        return definition_registry_service.update(
            db, definition_id, organization_id, payload, user.user_id
        )
    except OIKBError as exc:
        _raise(exc)


@router.post("/definitions/{definition_id}/versions", response_model=VersionRead, status_code=201)
def create_version(
    definition_id: UUID,
    payload: DefinitionVersionCreate,
    organization_id: UUID | None = None,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> object:
    _authorize(db, user, organization_id, OIKB_AUTHOR_ROLES)
    try:
        return definition_registry_service.create_version(
            db, definition_id, organization_id, payload, user.user_id
        )
    except OIKBError as exc:
        _raise(exc)


@router.get("/definitions/{definition_id}/versions", response_model=list[VersionRead])
def list_versions(
    definition_id: UUID,
    organization_id: UUID | None = None,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> object:
    _authorize(db, user, organization_id, OIKB_READ_ROLES)
    try:
        return definition_registry_service.list_versions(db, definition_id, organization_id)
    except OIKBError as exc:
        _raise(exc)


@router.get("/versions/{version_id}", response_model=VersionRead)
def get_version(
    version_id: UUID,
    organization_id: UUID | None = None,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> object:
    _authorize(db, user, organization_id, OIKB_READ_ROLES)
    try:
        return definition_registry_service.get_version(db, version_id, organization_id)
    except OIKBError as exc:
        _raise(exc)


def _transition(
    version_id: UUID,
    target: LifecycleStatus,
    payload: GovernanceAction,
    organization_id: UUID | None,
    db: Session,
    user: AuthenticatedUser,
) -> object:
    _authorize(db, user, organization_id, OIKB_GOVERNANCE_ROLES)
    try:
        return governance_service.transition(
            db, version_id, organization_id, target, payload, user.user_id
        )
    except OIKBError as exc:
        _raise(exc)


@router.post("/versions/{version_id}/submit-review", response_model=VersionRead)
def submit_review(
    version_id: UUID,
    payload: GovernanceAction,
    organization_id: UUID | None = None,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> object:
    return _transition(version_id, LifecycleStatus.IN_REVIEW, payload, organization_id, db, user)


@router.post("/versions/{version_id}/validate", response_model=VersionRead)
def validate_version(
    version_id: UUID,
    organization_id: UUID | None = None,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> object:
    _authorize(db, user, organization_id, OIKB_VALIDATION_ROLES)
    try:
        return governance_service.mark_validated(db, version_id, organization_id, user.user_id)
    except OIKBError as exc:
        _raise(exc)


@router.post("/versions/{version_id}/approve", response_model=VersionRead)
def approve_version(
    version_id: UUID,
    payload: GovernanceAction,
    organization_id: UUID | None = None,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> object:
    return _transition(version_id, LifecycleStatus.APPROVED, payload, organization_id, db, user)


@router.post("/versions/{version_id}/activate", response_model=VersionRead)
def activate_version(
    version_id: UUID,
    payload: GovernanceAction,
    organization_id: UUID | None = None,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> object:
    return _transition(version_id, LifecycleStatus.ACTIVE, payload, organization_id, db, user)


@router.post("/versions/{version_id}/deprecate", response_model=VersionRead)
def deprecate_version(
    version_id: UUID,
    payload: GovernanceAction,
    organization_id: UUID | None = None,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> object:
    return _transition(version_id, LifecycleStatus.DEPRECATED, payload, organization_id, db, user)


@router.post("/versions/{version_id}/retire", response_model=VersionRead)
def retire_version(
    version_id: UUID,
    payload: GovernanceAction,
    organization_id: UUID | None = None,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> object:
    return _transition(version_id, LifecycleStatus.RETIRED, payload, organization_id, db, user)


@router.post("/versions/{version_id}/reject", response_model=VersionRead)
def reject_version(
    version_id: UUID,
    payload: GovernanceAction,
    organization_id: UUID | None = None,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> object:
    return _transition(version_id, LifecycleStatus.REJECTED, payload, organization_id, db, user)


@router.post("/sources", status_code=201)
def create_source(
    payload: SourceCreate,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> object:
    _authorize(db, user, payload.owner_organization_id, OIKB_AUTHOR_ROLES)
    try:
        return source_citation_service.create(db, payload, payload.owner_organization_id)
    except OIKBError as exc:
        _raise(exc)


@router.get("/sources")
def list_sources(
    organization_id: UUID | None = None,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> object:
    _authorize(db, user, organization_id, OIKB_READ_ROLES)
    return source_citation_service.list(db, organization_id)


@router.post("/versions/{version_id}/sources", status_code=201)
def link_source(
    version_id: UUID,
    payload: SourceLinkCreate,
    organization_id: UUID | None = None,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> object:
    _authorize(db, user, organization_id, OIKB_AUTHOR_ROLES)
    try:
        version = definition_registry_service.get_version(db, version_id, organization_id)
        return source_citation_service.link(db, version, payload, organization_id)
    except OIKBError as exc:
        _raise(exc)


@router.post("/versions/{version_id}/validation-cases", status_code=201)
def create_validation_case(
    version_id: UUID,
    payload: ValidationCaseCreate,
    organization_id: UUID | None = None,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> object:
    _authorize(db, user, organization_id, OIKB_AUTHOR_ROLES)
    try:
        version = definition_registry_service.get_version(db, version_id, organization_id)
        return knowledge_validation_service.create_case(db, version, payload)
    except OIKBError as exc:
        _raise(exc)


@router.get("/versions/{version_id}/validation-cases")
def list_validation_cases(
    version_id: UUID,
    organization_id: UUID | None = None,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> object:
    _authorize(db, user, organization_id, OIKB_READ_ROLES)
    try:
        version = definition_registry_service.get_version(db, version_id, organization_id)
        return knowledge_validation_service.list_cases(db, version.id)
    except OIKBError as exc:
        _raise(exc)


@router.post("/versions/{version_id}/run-validation")
def run_validation(
    version_id: UUID,
    organization_id: UUID | None = None,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> object:
    _authorize(db, user, organization_id, OIKB_VALIDATION_ROLES)
    try:
        version = definition_registry_service.get_version(db, version_id, organization_id)
        return knowledge_validation_service.run(db, version, user.user_id)
    except OIKBError as exc:
        _raise(exc)


@router.post("/resolve", response_model=ResolutionRead)
def resolve_definition(
    payload: ResolveRequest,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> ResolutionRead:
    _authorize(db, user, payload.organization_id, OIKB_READ_ROLES)
    return knowledge_resolution_service.resolve_response(db, payload)


@router.get("/versions/{version_id}/execution-package", response_model=ExecutionPackage)
def export_execution_package(
    version_id: UUID,
    organization_id: UUID | None = None,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> ExecutionPackage:
    _authorize(db, user, organization_id, OIKB_READ_ROLES)
    try:
        version = definition_registry_service.get_version(db, version_id, organization_id)
        return execution_package_export_service.export(db, version)
    except OIKBError as exc:
        _raise(exc)


@router.get("/versions/{version_id}/audit")
def get_audit(
    version_id: UUID,
    organization_id: UUID | None = None,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> object:
    _authorize(db, user, organization_id, OIKB_READ_ROLES)
    try:
        version = definition_registry_service.get_version(db, version_id, organization_id)
        return list(
            db.scalars(
                select(OIKBChangeLog)
                .where(OIKBChangeLog.definition_version_id == version.id)
                .order_by(OIKBChangeLog.occurred_at)
            )
        )
    except OIKBError as exc:
        _raise(exc)
