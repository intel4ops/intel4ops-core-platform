from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.authorization import OrganizationAccess
from app.auth.commercial import require_commercial_entitlement
from app.auth.permissions import FINDING_READ_ROLES, INTELLIGENCE_EXECUTION_ROLES
from app.db.session import get_db
from app.schemas.value_scan import DirectionalValueScanCreate, DirectionalValueScanRead
from app.services.value_scan_service import ValueScanServiceError, directional_value_scan_service

router = APIRouter(
    prefix="/api/v1/organizations/{organization_id}/value-scans",
    tags=["directional-value-scan"],
)


def _raise(exc: ValueScanServiceError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status,
        detail={"code": exc.code, "message": str(exc)},
    ) from exc


def _response(row: object, is_current: bool) -> DirectionalValueScanRead:
    return DirectionalValueScanRead.model_validate(row).model_copy(
        update={"is_current": is_current}
    )


@router.post("", response_model=DirectionalValueScanRead)
def create_directional_value_scan(
    organization_id: UUID,
    payload: DirectionalValueScanCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(
        require_commercial_entitlement(
            "intelligence.findings",
            *INTELLIGENCE_EXECUTION_ROLES,
        )
    ),
) -> DirectionalValueScanRead:
    try:
        row, is_current = directional_value_scan_service.create(
            db,
            organization_id,
            access.user.user_id,
            payload.idempotency_key,
        )
    except ValueScanServiceError as exc:
        _raise(exc)
    return _response(row, is_current)


@router.get("/{scan_id}", response_model=DirectionalValueScanRead)
def get_directional_value_scan(
    organization_id: UUID,
    scan_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(
        require_commercial_entitlement("intelligence.findings", *FINDING_READ_ROLES)
    ),
) -> DirectionalValueScanRead:
    try:
        row, is_current = directional_value_scan_service.get(db, organization_id, scan_id)
    except ValueScanServiceError as exc:
        _raise(exc)
    return _response(row, is_current)
