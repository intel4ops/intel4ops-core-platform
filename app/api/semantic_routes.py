from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.authorization import OrganizationAccess, require_organization_roles
from app.auth.permissions import ANALYSIS_CASE_READ_ROLES
from app.db.session import get_db
from app.schemas.semantic import AnalysisCaseSemanticRead, DatasetSemanticRead
from app.services.analysis_case_semantic_service import analysis_case_semantic_service

router = APIRouter(prefix="/api/v1/organizations/{organization_id}/analysis-cases")


@router.get("/{case_id}/semantic", response_model=AnalysisCaseSemanticRead)
def get_case_semantic_view(
    organization_id: UUID,
    case_id: UUID,
    run_id: UUID | None = None,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ANALYSIS_CASE_READ_ROLES)),
) -> object:
    views = analysis_case_semantic_service.get_case_semantic_view(
        db, organization_id, case_id, run_id
    )
    return AnalysisCaseSemanticRead(
        analysis_case_id=case_id,
        run_id=run_id,
        datasets=[DatasetSemanticRead.model_validate(v, from_attributes=True) for v in views],
    )
