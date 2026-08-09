from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.authorization import OrganizationAccess
from app.auth.commercial import require_commercial_entitlement
from app.auth.permissions import INGESTION_READ_ROLES, ORGANIZATION_ADMIN_ROLES
from app.db.session import get_db
from app.schemas.operational_memory import (
    MemoryDecisionRequest,
    MemoryDetailRead,
    MemoryItemRead,
    MemoryListRead,
    MemoryRetrieveRead,
    MemoryRetrieveRequest,
    MemoryVersionRead,
)
from app.services.operational_memory_service import (
    OperationalMemoryServiceError,
    operational_memory_service,
)

router = APIRouter(
    prefix="/api/v1/organizations/{organization_id}/operational-memories",
    tags=["operational-memory"],
)


def _raise(exc: OperationalMemoryServiceError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status,
        detail={"code": exc.code, "message": str(exc)},
    ) from exc


def _detail(item: object, version: object) -> MemoryDetailRead:
    return MemoryDetailRead(
        item=MemoryItemRead.model_validate(item),
        current_version=MemoryVersionRead.model_validate(version),
    )


@router.get("", response_model=MemoryListRead)
def list_operational_memories(
    organization_id: UUID,
    category: str | None = Query(
        default=None, pattern="^(FIELD_MAPPING|SCHEMA_PATTERN|TERMINOLOGY)$"
    ),
    status: str | None = Query(
        default=None,
        pattern="^(OBSERVED|CONFIRMED|CORRECTED|AMBIGUOUS|REJECTED|DEPRECATED)$",
    ),
    source_system_family: str | None = Query(default=None, max_length=100),
    canonical_domain: str | None = Query(default=None, max_length=100),
    stale: bool | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=500),
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(
        require_commercial_entitlement("connect.canonical_mapping", *INGESTION_READ_ROLES)
    ),
) -> MemoryListRead:
    try:
        rows, next_cursor = operational_memory_service.list(
            db,
            organization_id,
            category=category,
            status=status,
            source_system_family=source_system_family,
            canonical_domain=canonical_domain,
            stale=stale,
            limit=limit,
            cursor=cursor,
        )
    except OperationalMemoryServiceError as exc:
        _raise(exc)
    return MemoryListRead(
        items=[MemoryItemRead.model_validate(row) for row in rows], next_cursor=next_cursor
    )


@router.get("/{memory_id}", response_model=MemoryDetailRead)
def get_operational_memory(
    organization_id: UUID,
    memory_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(
        require_commercial_entitlement("connect.canonical_mapping", *INGESTION_READ_ROLES)
    ),
) -> MemoryDetailRead:
    try:
        item, version = operational_memory_service.get(db, organization_id, memory_id)
    except OperationalMemoryServiceError as exc:
        _raise(exc)
    return _detail(item, version)


@router.post("/retrieve", response_model=MemoryRetrieveRead)
def retrieve_operational_memories(
    organization_id: UUID,
    payload: MemoryRetrieveRequest,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(
        require_commercial_entitlement("connect.canonical_mapping", *INGESTION_READ_ROLES)
    ),
) -> MemoryRetrieveRead:
    try:
        return operational_memory_service.retrieve(db, organization_id, payload)
    except OperationalMemoryServiceError as exc:
        _raise(exc)


@router.post("/{memory_id}/decisions", response_model=MemoryDetailRead)
def decide_operational_memory(
    organization_id: UUID,
    memory_id: UUID,
    payload: MemoryDecisionRequest,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(
        require_commercial_entitlement("connect.canonical_mapping", *ORGANIZATION_ADMIN_ROLES)
    ),
) -> MemoryDetailRead:
    actor_role = access.membership.role if access.membership else "platform_admin"
    try:
        item, version = operational_memory_service.decide(
            db,
            organization_id,
            memory_id,
            payload,
            access.user.user_id,
            actor_role,
        )
    except OperationalMemoryServiceError as exc:
        _raise(exc)
    return _detail(item, version)
