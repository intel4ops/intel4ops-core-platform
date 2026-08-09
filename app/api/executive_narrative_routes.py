from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.authorization import OrganizationAccess
from app.auth.commercial import require_commercial_entitlement
from app.auth.permissions import FINDING_READ_ROLES, INTELLIGENCE_EXECUTION_ROLES
from app.db.session import get_db
from app.schemas.executive_narrative import (
    ExecutiveNarrativeCreate,
    GroundedExecutiveNarrativeList,
    GroundedExecutiveNarrativeRead,
)
from app.services.executive_narrative_service import (
    ExecutiveNarrativeServiceError,
    executive_narrative_service,
)

router = APIRouter(
    prefix="/api/v1/organizations/{organization_id}/executive-narratives",
    tags=["grounded-executive-narrative"],
)


def _raise(exc: ExecutiveNarrativeServiceError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status,
        detail={"code": exc.code, "message": str(exc)},
    ) from exc


@router.post(
    "",
    response_model=GroundedExecutiveNarrativeRead,
    status_code=status.HTTP_201_CREATED,
)
def create_executive_narrative(
    organization_id: UUID,
    payload: ExecutiveNarrativeCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(
        require_commercial_entitlement(
            "intelligence.findings",
            *INTELLIGENCE_EXECUTION_ROLES,
        )
    ),
) -> GroundedExecutiveNarrativeRead:
    try:
        row = executive_narrative_service.create(db, organization_id, access.user.user_id, payload)
    except ExecutiveNarrativeServiceError as exc:
        _raise(exc)
    return GroundedExecutiveNarrativeRead.model_validate(row)


@router.get("", response_model=GroundedExecutiveNarrativeList)
def list_executive_narratives(
    organization_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(
        require_commercial_entitlement("intelligence.findings", *FINDING_READ_ROLES)
    ),
) -> GroundedExecutiveNarrativeList:
    return GroundedExecutiveNarrativeList(
        items=[
            GroundedExecutiveNarrativeRead.model_validate(row)
            for row in executive_narrative_service.list_for_organization(db, organization_id)
        ]
    )


@router.get("/{narrative_id}", response_model=GroundedExecutiveNarrativeRead)
def get_executive_narrative(
    organization_id: UUID,
    narrative_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(
        require_commercial_entitlement("intelligence.findings", *FINDING_READ_ROLES)
    ),
) -> GroundedExecutiveNarrativeRead:
    try:
        row = executive_narrative_service.get(db, organization_id, narrative_id)
    except ExecutiveNarrativeServiceError as exc:
        _raise(exc)
    return GroundedExecutiveNarrativeRead.model_validate(row)
