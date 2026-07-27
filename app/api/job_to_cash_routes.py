from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.authorization import OrganizationAccess
from app.auth.commercial import require_commercial_entitlement
from app.auth.permissions import ORGANIZATION_ADMIN_ROLES
from app.db.session import get_db
from app.schemas.job_to_cash import JobToCashRunCreate, JobToCashRunRead
from app.services.job_to_cash_orchestration_service import job_to_cash_orchestration_service

router = APIRouter(
    prefix="/api/v1/organizations/{organization_id}/job-to-cash",
    tags=["Job-to-Cash"],
    dependencies=[
        Depends(require_commercial_entitlement(key, *ORGANIZATION_ADMIN_ROLES))
        for key in (
            "product.I4O-CONNECT",
            "product.I4O-TRUST",
            "product.I4O-INTEL",
            "product.I4O-RECOVERY",
            "commercial.api_access",
        )
    ],
)


@router.post("/runs", response_model=JobToCashRunRead, status_code=201)
def execute(
    organization_id: UUID,
    payload: JobToCashRunCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(
        require_commercial_entitlement("industry.job_to_cash", *ORGANIZATION_ADMIN_ROLES)
    ),
) -> object:
    return job_to_cash_orchestration_service.execute(
        db, organization_id, payload, access.user.user_id
    )
