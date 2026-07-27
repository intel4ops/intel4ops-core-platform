from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.auth.authorization import OrganizationAccess, require_organization_roles
from app.auth.commercial import require_commercial_entitlement
from app.auth.permissions import (
    RELIABILITY_ASSESSMENT_REVIEW_ROLES,
    RELIABILITY_EXECUTION_READ_ROLES,
    RELIABILITY_EXECUTION_RUN_ROLES,
    RELIABILITY_METHOD_READ_ROLES,
)
from app.db.session import get_db
from app.models.reliability import (
    ReliabilityExecutionStep,
    ReliabilityMetric,
    ReliabilityModelResult,
)
from app.schemas.reliability import (
    ReliabilityEvaluateRequest,
    ReliabilityEvaluationRead,
    ReliabilityExecutionCreate,
    ReliabilityExecutionPage,
    ReliabilityExecutionRead,
    ReliabilityMethodRead,
    ReliabilityReviewCreate,
)
from app.services.reliability_service import (
    ReliabilityServiceError,
    reliability_execution_service,
)

router = APIRouter(
    prefix="/api/v1/organizations/{organization_id}/reliability",
    dependencies=[
        Depends(
            require_commercial_entitlement(
                "intelligence.reliability", *RELIABILITY_EXECUTION_READ_ROLES
            )
        )
    ],
)


def _raise(exc: ReliabilityServiceError) -> NoReturn:
    raise HTTPException(
        status_code=exc.http_status, detail={"code": exc.code, "message": str(exc)}
    ) from exc


@router.post(
    "/executions", response_model=ReliabilityExecutionRead, status_code=status.HTTP_201_CREATED
)
def create_execution(
    organization_id: UUID,
    payload: ReliabilityExecutionCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(
        require_organization_roles(*RELIABILITY_EXECUTION_RUN_ROLES)
    ),
) -> object:
    try:
        return reliability_execution_service.execute(
            db, organization_id, payload, access.user.user_id
        )
    except ReliabilityServiceError as exc:
        _raise(exc)


@router.get("/executions", response_model=ReliabilityExecutionPage)
def list_executions(
    organization_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*RELIABILITY_EXECUTION_READ_ROLES)),
) -> ReliabilityExecutionPage:
    rows, total = reliability_execution_service.list_executions(
        db, organization_id, page, page_size
    )
    return ReliabilityExecutionPage(items=rows, page=page, page_size=page_size, total=total)


@router.get("/executions/{execution_id}", response_model=ReliabilityExecutionRead)
def get_execution(
    organization_id: UUID,
    execution_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*RELIABILITY_EXECUTION_READ_ROLES)),
) -> object:
    try:
        return reliability_execution_service.get(db, organization_id, execution_id)
    except ReliabilityServiceError as exc:
        _raise(exc)


def _children(db: Session, organization_id: UUID, execution_id: UUID, model: type) -> object:
    try:
        return jsonable_encoder(
            reliability_execution_service.children(db, organization_id, execution_id, model)
        )
    except ReliabilityServiceError as exc:
        _raise(exc)


@router.get("/executions/{execution_id}/metrics")
def metrics(
    organization_id: UUID,
    execution_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*RELIABILITY_EXECUTION_READ_ROLES)),
) -> object:
    return _children(db, organization_id, execution_id, ReliabilityMetric)


@router.get("/executions/{execution_id}/models")
@router.get("/executions/{execution_id}/survival")
@router.get("/executions/{execution_id}/risks")
@router.get("/executions/{execution_id}/health")
@router.get("/executions/{execution_id}/bad-actors")
@router.get("/executions/{execution_id}/repeat-failures")
@router.get("/executions/{execution_id}/maintenance-effectiveness")
@router.get("/executions/{execution_id}/pm-intervals")
def model_results(
    organization_id: UUID,
    execution_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*RELIABILITY_EXECUTION_READ_ROLES)),
) -> object:
    return _children(db, organization_id, execution_id, ReliabilityModelResult)


@router.get("/executions/{execution_id}/trace")
def trace(
    organization_id: UUID,
    execution_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*RELIABILITY_EXECUTION_READ_ROLES)),
) -> object:
    return _children(db, organization_id, execution_id, ReliabilityExecutionStep)


@router.get("/executions/{execution_id}/evidence")
def evidence(
    organization_id: UUID,
    execution_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*RELIABILITY_EXECUTION_READ_ROLES)),
) -> dict[str, object]:
    row = reliability_execution_service.get(db, organization_id, execution_id)
    return {
        "reliability_execution_id": row.id,
        "definition_version_id": row.oikb_definition_version_id,
        "dataset_fingerprint": row.dataset_fingerprint,
        "lifecycle_fingerprint": row.lifecycle_fingerprint,
        "trust_assessment_id": row.trust_assessment_id,
        "readiness_assessment_id": row.readiness_assessment_id,
        "failure_definition": row.failure_definition_code,
        "exposure_basis": row.exposure_basis,
        "explanation": row.explanation,
        "raw_records_included": False,
    }


@router.post("/evaluate", response_model=ReliabilityEvaluationRead)
@router.post("/validate-definition", response_model=ReliabilityEvaluationRead)
def evaluate(
    organization_id: UUID,
    payload: ReliabilityEvaluateRequest,
    _: OrganizationAccess = Depends(require_organization_roles(*RELIABILITY_EXECUTION_RUN_ROLES)),
) -> ReliabilityEvaluationRead:
    del organization_id
    try:
        return reliability_execution_service.evaluate(payload)
    except ReliabilityServiceError as exc:
        _raise(exc)


@router.get("/methods", response_model=list[ReliabilityMethodRead])
def methods(
    organization_id: UUID,
    _: OrganizationAccess = Depends(require_organization_roles(*RELIABILITY_METHOD_READ_ROLES)),
) -> list[ReliabilityMethodRead]:
    del organization_id
    return [
        ReliabilityMethodRead.model_validate(method.metadata)
        for method in reliability_execution_service.registry.list()
    ]


@router.get("/methods/{method_code}", response_model=ReliabilityMethodRead)
def method(
    organization_id: UUID,
    method_code: str,
    _: OrganizationAccess = Depends(require_organization_roles(*RELIABILITY_METHOD_READ_ROLES)),
) -> ReliabilityMethodRead:
    del organization_id
    try:
        row = reliability_execution_service.registry.get(method_code)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Reliability method not found") from exc
    return ReliabilityMethodRead.model_validate(row.metadata)


@router.post("/executions/{execution_id}/reviews", status_code=201)
def review(
    organization_id: UUID,
    execution_id: UUID,
    payload: ReliabilityReviewCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(
        require_organization_roles(*RELIABILITY_ASSESSMENT_REVIEW_ROLES)
    ),
) -> object:
    try:
        return jsonable_encoder(
            reliability_execution_service.review(
                db, organization_id, execution_id, payload, access.user.user_id
            )
        )
    except ReliabilityServiceError as exc:
        _raise(exc)
