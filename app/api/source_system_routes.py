from collections.abc import Callable
from typing import NoReturn, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.authorization import OrganizationAccess, require_organization_roles
from app.auth.commercial import require_commercial_entitlement
from app.auth.permissions import (
    SOURCE_SYSTEM_ADMIN_ROLES,
    SOURCE_SYSTEM_OPERATIONS_ROLES,
    SOURCE_SYSTEM_READ_ROLES,
)
from app.db.session import get_db
from app.models.source_system import (
    DataClassification,
    IntegrationMethod,
    SourceEnvironment,
    SourceHealthStatus,
    SourceSystem,
    SourceSystemStatus,
    SourceSystemType,
)
from app.schemas.source_systems import (
    SourceSystemCreate,
    SourceSystemHealthUpdate,
    SourceSystemRead,
    SourceSystemUpdate,
)
from app.services.source_system_service import (
    DuplicateSourceSystemCodeError,
    InvalidSourceSystemTransitionError,
    SourceSystemNotFoundError,
    SourceSystemOrganizationNotFoundError,
    source_system_service,
)

router = APIRouter(
    prefix="/api/v1/organizations/{organization_id}/source-systems",
    dependencies=[
        Depends(require_commercial_entitlement("connect.source_systems", *SOURCE_SYSTEM_READ_ROLES))
    ],
)


def _translate_error(exc: Exception) -> NoReturn:
    if isinstance(exc, (DuplicateSourceSystemCodeError, InvalidSourceSystemTransitionError)):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("", response_model=SourceSystemRead, status_code=status.HTTP_201_CREATED)
def create_source_system(
    organization_id: UUID,
    payload: SourceSystemCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*SOURCE_SYSTEM_ADMIN_ROLES)),
) -> SourceSystem:
    try:
        return source_system_service.create(db, organization_id, payload, access.user.user_id)
    except (
        DuplicateSourceSystemCodeError,
        SourceSystemOrganizationNotFoundError,
    ) as exc:
        _translate_error(exc)


@router.get("", response_model=list[SourceSystemRead])
def list_source_systems(
    organization_id: UUID,
    system_type: SourceSystemType | None = None,
    provider: str | None = None,
    integration_method: IntegrationMethod | None = None,
    environment: SourceEnvironment | None = None,
    source_status: SourceSystemStatus | None = Query(default=None, alias="status"),
    health_status: SourceHealthStatus | None = None,
    data_classification: DataClassification | None = None,
    is_active: bool | None = None,
    search: str | None = Query(default=None, max_length=200),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*SOURCE_SYSTEM_READ_ROLES)),
) -> list[SourceSystem]:
    return source_system_service.list(
        db,
        organization_id,
        system_type=system_type,
        provider=provider,
        integration_method=integration_method,
        environment=environment,
        status=source_status,
        health_status=health_status,
        data_classification=data_classification,
        is_active=is_active,
        search=search,
        offset=offset,
        limit=limit,
    )


@router.get("/{source_system_id}", response_model=SourceSystemRead)
def get_source_system(
    organization_id: UUID,
    source_system_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*SOURCE_SYSTEM_READ_ROLES)),
) -> SourceSystem:
    try:
        return source_system_service.get(db, organization_id, source_system_id)
    except SourceSystemNotFoundError as exc:
        _translate_error(exc)


@router.patch("/{source_system_id}", response_model=SourceSystemRead)
def update_source_system(
    organization_id: UUID,
    source_system_id: UUID,
    payload: SourceSystemUpdate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*SOURCE_SYSTEM_ADMIN_ROLES)),
) -> SourceSystem:
    try:
        return source_system_service.update(
            db, organization_id, source_system_id, payload, access.user.user_id
        )
    except (
        SourceSystemNotFoundError,
        DuplicateSourceSystemCodeError,
        InvalidSourceSystemTransitionError,
    ) as exc:
        _translate_error(exc)


def _status_action(
    action: str,
    db: Session,
    organization_id: UUID,
    source_system_id: UUID,
    actor_user_id: UUID,
) -> SourceSystem:
    try:
        method = cast(
            Callable[[Session, UUID, UUID, UUID], SourceSystem],
            getattr(source_system_service, action),
        )
        return method(db, organization_id, source_system_id, actor_user_id)
    except (SourceSystemNotFoundError, InvalidSourceSystemTransitionError) as exc:
        _translate_error(exc)


@router.post("/{source_system_id}/pause", response_model=SourceSystemRead)
def pause_source_system(
    organization_id: UUID,
    source_system_id: UUID,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*SOURCE_SYSTEM_ADMIN_ROLES)),
) -> SourceSystem:
    return _status_action("pause", db, organization_id, source_system_id, access.user.user_id)


@router.post("/{source_system_id}/reactivate", response_model=SourceSystemRead)
def reactivate_source_system(
    organization_id: UUID,
    source_system_id: UUID,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*SOURCE_SYSTEM_ADMIN_ROLES)),
) -> SourceSystem:
    return _status_action("reactivate", db, organization_id, source_system_id, access.user.user_id)


@router.post("/{source_system_id}/decommission", response_model=SourceSystemRead)
def decommission_source_system(
    organization_id: UUID,
    source_system_id: UUID,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*SOURCE_SYSTEM_ADMIN_ROLES)),
) -> SourceSystem:
    return _status_action(
        "decommission", db, organization_id, source_system_id, access.user.user_id
    )


@router.post("/{source_system_id}/connection-success", response_model=SourceSystemRead)
def record_connection_success(
    organization_id: UUID,
    source_system_id: UUID,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(
        require_organization_roles(*SOURCE_SYSTEM_OPERATIONS_ROLES)
    ),
) -> SourceSystem:
    return _status_action(
        "record_connection_success",
        db,
        organization_id,
        source_system_id,
        access.user.user_id,
    )


@router.post("/{source_system_id}/connection-failure", response_model=SourceSystemRead)
def record_connection_failure(
    organization_id: UUID,
    source_system_id: UUID,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(
        require_organization_roles(*SOURCE_SYSTEM_OPERATIONS_ROLES)
    ),
) -> SourceSystem:
    return _status_action(
        "record_connection_failure",
        db,
        organization_id,
        source_system_id,
        access.user.user_id,
    )


@router.post("/{source_system_id}/health", response_model=SourceSystemRead)
def update_source_system_health(
    organization_id: UUID,
    source_system_id: UUID,
    payload: SourceSystemHealthUpdate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(
        require_organization_roles(*SOURCE_SYSTEM_OPERATIONS_ROLES)
    ),
) -> SourceSystem:
    try:
        return source_system_service.update_health(
            db,
            organization_id,
            source_system_id,
            payload.health_status,
            access.user.user_id,
        )
    except (SourceSystemNotFoundError, InvalidSourceSystemTransitionError) as exc:
        _translate_error(exc)
