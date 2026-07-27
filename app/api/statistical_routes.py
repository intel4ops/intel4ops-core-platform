from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.authorization import OrganizationAccess, require_organization_roles
from app.auth.commercial import require_commercial_entitlement
from app.auth.permissions import (
    STATISTICAL_EXECUTION_READ_ROLES,
    STATISTICAL_EXECUTION_RUN_ROLES,
    STATISTICAL_METHOD_READ_ROLES,
    STATISTICAL_REVIEW_ROLES,
    STATISTICAL_SUPPRESSION_MANAGE_ROLES,
)
from app.db.session import get_db
from app.models.statistics import StatisticalExecutionStatus
from app.schemas.statistics import (
    ObservationReviewCreate,
    ObservationReviewRead,
    ObservationSuppressionCreate,
    ObservationSuppressionRead,
    StatisticalBaselineRead,
    StatisticalEvaluateRequest,
    StatisticalEvaluationRead,
    StatisticalExecutionCreate,
    StatisticalExecutionDetail,
    StatisticalExecutionPage,
    StatisticalExecutionRead,
    StatisticalExecutionStepRead,
    StatisticalMethodRead,
    StatisticalObservationRead,
)
from app.services.statistical_service import (
    StatisticalServiceError,
    statistical_execution_service,
)

router = APIRouter(
    prefix="/api/v1/organizations/{organization_id}/statistics",
    dependencies=[
        Depends(
            require_commercial_entitlement(
                "intelligence.statistics", *STATISTICAL_EXECUTION_READ_ROLES
            )
        )
    ],
)


def _raise(exc: StatisticalServiceError) -> NoReturn:
    raise HTTPException(
        status_code=exc.http_status,
        detail={"code": exc.code, "message": str(exc)},
    ) from exc


@router.post(
    "/executions",
    response_model=StatisticalExecutionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_execution(
    organization_id: UUID,
    payload: StatisticalExecutionCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(
        require_organization_roles(*STATISTICAL_EXECUTION_RUN_ROLES)
    ),
) -> object:
    try:
        return statistical_execution_service.execute(
            db, organization_id, payload, access.user.user_id
        )
    except StatisticalServiceError as exc:
        _raise(exc)


@router.get("/executions", response_model=StatisticalExecutionPage)
def list_executions(
    organization_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    status_filter: StatisticalExecutionStatus | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*STATISTICAL_EXECUTION_READ_ROLES)),
) -> StatisticalExecutionPage:
    items, total = statistical_execution_service.list_executions(
        db,
        organization_id,
        page=page,
        page_size=page_size,
        status=status_filter.value if status_filter else None,
    )
    return StatisticalExecutionPage(items=items, page=page, page_size=page_size, total=total)


@router.get("/executions/{execution_id}", response_model=StatisticalExecutionDetail)
def get_execution(
    organization_id: UUID,
    execution_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*STATISTICAL_EXECUTION_READ_ROLES)),
) -> StatisticalExecutionDetail:
    try:
        execution = statistical_execution_service.get(db, organization_id, execution_id)
        return StatisticalExecutionDetail(
            **StatisticalExecutionRead.model_validate(execution).model_dump(),
            baselines=statistical_execution_service.baselines_for(
                db, organization_id, execution_id
            ),
            observations=statistical_execution_service.observations_for(
                db, organization_id, execution_id
            ),
            steps=statistical_execution_service.steps_for(db, organization_id, execution_id),
        )
    except StatisticalServiceError as exc:
        _raise(exc)


@router.get("/executions/{execution_id}/baseline", response_model=list[StatisticalBaselineRead])
def get_baseline(
    organization_id: UUID,
    execution_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*STATISTICAL_EXECUTION_READ_ROLES)),
) -> object:
    try:
        return statistical_execution_service.baselines_for(db, organization_id, execution_id)
    except StatisticalServiceError as exc:
        _raise(exc)


@router.get(
    "/executions/{execution_id}/observations",
    response_model=list[StatisticalObservationRead],
)
def get_observations(
    organization_id: UUID,
    execution_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*STATISTICAL_EXECUTION_READ_ROLES)),
) -> object:
    try:
        return statistical_execution_service.observations_for(db, organization_id, execution_id)
    except StatisticalServiceError as exc:
        _raise(exc)


@router.get(
    "/executions/{execution_id}/trace",
    response_model=list[StatisticalExecutionStepRead],
)
def get_trace(
    organization_id: UUID,
    execution_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*STATISTICAL_EXECUTION_READ_ROLES)),
) -> object:
    try:
        return statistical_execution_service.steps_for(db, organization_id, execution_id)
    except StatisticalServiceError as exc:
        _raise(exc)


@router.get("/executions/{execution_id}/evidence")
def get_evidence(
    organization_id: UUID,
    execution_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*STATISTICAL_EXECUTION_READ_ROLES)),
) -> dict[str, object]:
    try:
        observations = statistical_execution_service.observations_for(
            db, organization_id, execution_id
        )
        return {
            "execution_id": execution_id,
            "evidence": [
                evidence
                for observation in observations
                for evidence in observation.evidence_references
            ],
            "raw_records_included": False,
        }
    except StatisticalServiceError as exc:
        _raise(exc)


@router.post("/evaluate", response_model=StatisticalEvaluationRead)
def evaluate(
    organization_id: UUID,
    payload: StatisticalEvaluateRequest,
    _: OrganizationAccess = Depends(require_organization_roles(*STATISTICAL_EXECUTION_RUN_ROLES)),
) -> StatisticalEvaluationRead:
    del organization_id
    return statistical_execution_service.evaluate(payload)


@router.post("/validate-definition", response_model=StatisticalEvaluationRead)
def validate_definition(
    organization_id: UUID,
    payload: StatisticalEvaluateRequest,
    _: OrganizationAccess = Depends(require_organization_roles(*STATISTICAL_EXECUTION_RUN_ROLES)),
) -> StatisticalEvaluationRead:
    del organization_id
    return statistical_execution_service.evaluate(payload)


@router.get("/methods", response_model=list[StatisticalMethodRead])
def list_methods(
    organization_id: UUID,
    _: OrganizationAccess = Depends(require_organization_roles(*STATISTICAL_METHOD_READ_ROLES)),
) -> list[StatisticalMethodRead]:
    del organization_id
    return [
        StatisticalMethodRead.model_validate(method.metadata, from_attributes=True)
        for method in statistical_execution_service.registry.list()
    ]


@router.get("/methods/{method_code}", response_model=StatisticalMethodRead)
def get_method(
    organization_id: UUID,
    method_code: str,
    _: OrganizationAccess = Depends(require_organization_roles(*STATISTICAL_METHOD_READ_ROLES)),
) -> StatisticalMethodRead:
    del organization_id
    try:
        method = statistical_execution_service.registry.get(method_code)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Statistical method not found") from exc
    return StatisticalMethodRead.model_validate(method.metadata, from_attributes=True)


@router.get("/observations/{observation_id}", response_model=StatisticalObservationRead)
def get_observation(
    organization_id: UUID,
    observation_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*STATISTICAL_EXECUTION_READ_ROLES)),
) -> object:
    try:
        return statistical_execution_service.observation(db, organization_id, observation_id)
    except StatisticalServiceError as exc:
        _raise(exc)


@router.post(
    "/observations/{observation_id}/review",
    response_model=ObservationReviewRead,
    status_code=status.HTTP_201_CREATED,
)
def review_observation(
    organization_id: UUID,
    observation_id: UUID,
    payload: ObservationReviewCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*STATISTICAL_REVIEW_ROLES)),
) -> object:
    try:
        return statistical_execution_service.review(
            db, organization_id, observation_id, payload, access.user.user_id
        )
    except StatisticalServiceError as exc:
        _raise(exc)


@router.post(
    "/observations/{observation_id}/suppress",
    response_model=ObservationSuppressionRead,
    status_code=status.HTTP_201_CREATED,
)
def suppress_observation(
    organization_id: UUID,
    observation_id: UUID,
    payload: ObservationSuppressionCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(
        require_organization_roles(*STATISTICAL_SUPPRESSION_MANAGE_ROLES)
    ),
) -> object:
    try:
        return statistical_execution_service.suppress(
            db, organization_id, observation_id, payload, access.user.user_id
        )
    except StatisticalServiceError as exc:
        _raise(exc)
