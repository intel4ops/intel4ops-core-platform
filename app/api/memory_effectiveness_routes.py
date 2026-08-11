from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.authorization import OrganizationAccess
from app.auth.commercial import require_commercial_entitlement
from app.auth.permissions import INGESTION_READ_ROLES
from app.db.session import get_db
from app.schemas.memory_effectiveness import MemoryEffectivenessRead
from app.services.memory_effectiveness_service import memory_effectiveness_service

router = APIRouter(
    prefix="/api/v1/organizations/{organization_id}/canonical-mapping",
    tags=["canonical-mapping-memory-effectiveness"],
)


@router.get("/memory-effectiveness", response_model=MemoryEffectivenessRead)
def memory_effectiveness(
    organization_id: UUID,
    source_schema_id: UUID | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(
        require_commercial_entitlement("connect.canonical_mapping", *INGESTION_READ_ROLES)
    ),
) -> MemoryEffectivenessRead:
    return memory_effectiveness_service.report(
        db,
        organization_id,
        source_schema_id=source_schema_id,
        date_from=date_from,
        date_to=date_to,
    )
