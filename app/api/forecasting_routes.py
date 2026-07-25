from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.authorization import OrganizationAccess, require_organization_roles
from app.auth.permissions import (
    FORECAST_ACCURACY_READ_ROLES,
    FORECAST_ACTUAL_REGISTER_ROLES,
    FORECAST_EXECUTION_READ_ROLES,
    FORECAST_EXECUTION_RUN_ROLES,
    FORECAST_METHOD_READ_ROLES,
    FORECAST_REVISION_CREATE_ROLES,
    FORECAST_SCENARIO_CREATE_ROLES,
)
from app.db.session import get_db
from app.models.forecasting import (
    ForecastAccuracyResult,
    ForecastBacktest,
    ForecastCandidate,
    ForecastExecutionStep,
    ForecastMetric,
    ForecastPoint,
    ForecastRevision,
    ForecastScenario,
)
from app.schemas.forecasting import (
    ForecastActualCreate,
    ForecastActualRead,
    ForecastCandidateRead,
    ForecastEvaluateRequest,
    ForecastEvaluationRead,
    ForecastExecutionCreate,
    ForecastExecutionPage,
    ForecastExecutionRead,
    ForecastMethodRead,
    ForecastPointRead,
    ForecastRevisionCreate,
    ForecastScenarioCreate,
    ForecastScenarioRead,
)
from app.services.forecasting_service import (
    ForecastingServiceError,
    forecast_execution_service,
)

router = APIRouter(prefix="/api/v1/organizations/{organization_id}/forecasts")


def _raise(exc: ForecastingServiceError) -> NoReturn:
    raise HTTPException(
        status_code=exc.http_status, detail={"code": exc.code, "message": str(exc)}
    ) from exc


@router.post(
    "/executions", response_model=ForecastExecutionRead, status_code=status.HTTP_201_CREATED
)
def create_execution(
    organization_id: UUID,
    payload: ForecastExecutionCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*FORECAST_EXECUTION_RUN_ROLES)),
) -> object:
    try:
        return forecast_execution_service.execute(db, organization_id, payload, access.user.user_id)
    except ForecastingServiceError as exc:
        _raise(exc)


@router.get("/executions", response_model=ForecastExecutionPage)
def list_executions(
    organization_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*FORECAST_EXECUTION_READ_ROLES)),
) -> ForecastExecutionPage:
    items, total = forecast_execution_service.list_executions(db, organization_id, page, page_size)
    return ForecastExecutionPage(items=items, page=page, page_size=page_size, total=total)


@router.get("/executions/{execution_id}", response_model=ForecastExecutionRead)
def get_execution(
    organization_id: UUID,
    execution_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*FORECAST_EXECUTION_READ_ROLES)),
) -> object:
    try:
        return forecast_execution_service.get(db, organization_id, execution_id)
    except ForecastingServiceError as exc:
        _raise(exc)


def _children(db: Session, organization_id: UUID, execution_id: UUID, model: type) -> list[object]:
    try:
        return forecast_execution_service.children(db, organization_id, execution_id, model)
    except ForecastingServiceError as exc:
        _raise(exc)


@router.get("/executions/{execution_id}/candidates", response_model=list[ForecastCandidateRead])
def candidates(
    organization_id: UUID,
    execution_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*FORECAST_EXECUTION_READ_ROLES)),
) -> list[object]:
    return _children(db, organization_id, execution_id, ForecastCandidate)


@router.get("/executions/{execution_id}/backtests")
def backtests(
    organization_id: UUID,
    execution_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*FORECAST_EXECUTION_READ_ROLES)),
) -> object:
    return jsonable_encoder(_children(db, organization_id, execution_id, ForecastBacktest))


@router.get("/executions/{execution_id}/metrics")
def metrics(
    organization_id: UUID,
    execution_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*FORECAST_EXECUTION_READ_ROLES)),
) -> object:
    return jsonable_encoder(_children(db, organization_id, execution_id, ForecastMetric))


@router.get("/executions/{execution_id}/points", response_model=list[ForecastPointRead])
def points(
    organization_id: UUID,
    execution_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*FORECAST_EXECUTION_READ_ROLES)),
) -> list[object]:
    return _children(db, organization_id, execution_id, ForecastPoint)


@router.get("/executions/{execution_id}/trace")
def trace(
    organization_id: UUID,
    execution_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*FORECAST_EXECUTION_READ_ROLES)),
) -> object:
    return jsonable_encoder(_children(db, organization_id, execution_id, ForecastExecutionStep))


@router.get("/executions/{execution_id}/evidence")
def evidence(
    organization_id: UUID,
    execution_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*FORECAST_EXECUTION_READ_ROLES)),
) -> dict[str, object]:
    execution = forecast_execution_service.get(db, organization_id, execution_id)
    return {
        "forecast_execution_id": execution.id,
        "definition_version_id": execution.oikb_definition_version_id,
        "dataset_fingerprint": execution.dataset_fingerprint,
        "prepared_series_fingerprint": execution.prepared_series_fingerprint,
        "trust_assessment_id": execution.trust_assessment_id,
        "readiness_assessment_id": execution.readiness_assessment_id,
        "explanation": execution.explanation,
        "raw_records_included": False,
    }


@router.post("/evaluate", response_model=ForecastEvaluationRead)
def evaluate(
    organization_id: UUID,
    payload: ForecastEvaluateRequest,
    _: OrganizationAccess = Depends(require_organization_roles(*FORECAST_EXECUTION_RUN_ROLES)),
) -> ForecastEvaluationRead:
    del organization_id
    return forecast_execution_service.evaluate(payload)


@router.post("/validate-definition", response_model=ForecastEvaluationRead)
def validate_definition(
    organization_id: UUID,
    payload: ForecastEvaluateRequest,
    _: OrganizationAccess = Depends(require_organization_roles(*FORECAST_EXECUTION_RUN_ROLES)),
) -> ForecastEvaluationRead:
    del organization_id
    return forecast_execution_service.evaluate(payload)


@router.get("/methods", response_model=list[ForecastMethodRead])
def methods(
    organization_id: UUID,
    _: OrganizationAccess = Depends(require_organization_roles(*FORECAST_METHOD_READ_ROLES)),
) -> list[ForecastMethodRead]:
    del organization_id
    return [
        ForecastMethodRead.model_validate(method.metadata, from_attributes=True)
        for method in forecast_execution_service.registry.list()
    ]


@router.get("/methods/{method_code}", response_model=ForecastMethodRead)
def method(
    organization_id: UUID,
    method_code: str,
    _: OrganizationAccess = Depends(require_organization_roles(*FORECAST_METHOD_READ_ROLES)),
) -> ForecastMethodRead:
    del organization_id
    try:
        result = forecast_execution_service.registry.get(method_code)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Forecast method not found") from exc
    return ForecastMethodRead.model_validate(result.metadata, from_attributes=True)


@router.post(
    "/executions/{execution_id}/scenarios", response_model=ForecastScenarioRead, status_code=201
)
def create_scenario(
    organization_id: UUID,
    execution_id: UUID,
    payload: ForecastScenarioCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(
        require_organization_roles(*FORECAST_SCENARIO_CREATE_ROLES)
    ),
) -> object:
    try:
        return forecast_execution_service.create_scenario(
            db, organization_id, execution_id, payload, access.user.user_id
        )
    except ForecastingServiceError as exc:
        _raise(exc)


@router.get("/executions/{execution_id}/scenarios", response_model=list[ForecastScenarioRead])
def scenarios(
    organization_id: UUID,
    execution_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*FORECAST_EXECUTION_READ_ROLES)),
) -> list[object]:
    return _children(db, organization_id, execution_id, ForecastScenario)


@router.post("/executions/{execution_id}/revise")
def revise(
    organization_id: UUID,
    execution_id: UUID,
    payload: ForecastRevisionCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(
        require_organization_roles(*FORECAST_REVISION_CREATE_ROLES)
    ),
) -> object:
    try:
        return jsonable_encoder(
            forecast_execution_service.revise(
                db, organization_id, execution_id, payload, access.user.user_id
            )
        )
    except ForecastingServiceError as exc:
        _raise(exc)


@router.get("/executions/{execution_id}/revisions")
def revisions(
    organization_id: UUID,
    execution_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*FORECAST_EXECUTION_READ_ROLES)),
) -> object:
    forecast_execution_service.get(db, organization_id, execution_id)
    return jsonable_encoder(
        list(
            db.scalars(
                select(ForecastRevision).where(
                    ForecastRevision.organization_id == organization_id,
                    ForecastRevision.prior_forecast_execution_id == execution_id,
                )
            )
        )
    )


@router.post("/points/{forecast_point_id}/actual", response_model=ForecastActualRead)
def actual(
    organization_id: UUID,
    forecast_point_id: UUID,
    payload: ForecastActualCreate,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*FORECAST_ACTUAL_REGISTER_ROLES)),
) -> object:
    try:
        return forecast_execution_service.register_actual(
            db, organization_id, forecast_point_id, payload
        )
    except ForecastingServiceError as exc:
        _raise(exc)


@router.get("/executions/{execution_id}/accuracy")
def accuracy(
    organization_id: UUID,
    execution_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*FORECAST_ACCURACY_READ_ROLES)),
) -> object:
    forecast_execution_service.get(db, organization_id, execution_id)
    return jsonable_encoder(
        list(
            db.scalars(
                select(ForecastAccuracyResult).where(
                    ForecastAccuracyResult.organization_id == organization_id,
                    ForecastAccuracyResult.forecast_execution_id == execution_id,
                )
            )
        )
    )
