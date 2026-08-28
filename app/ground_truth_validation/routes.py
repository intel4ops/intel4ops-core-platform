from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.authorization import OrganizationAccess, require_organization_roles
from app.auth.permissions import VALIDATION_READ_ROLES, VALIDATION_WRITE_ROLES
from app.db.session import get_db
from app.ground_truth_validation.repository import validation_ground_truth_repository
from app.ground_truth_validation.service import ValidationServiceError, validation_service
from app.schemas.ground_truth_validation import (
    GroundTruthRead,
    GroundTruthUpload,
    ValidationResultRead,
    ValidationResultsHistoryRead,
    ValidationSimulationCreate,
    ValidationSimulationDetail,
    ValidationSimulationRead,
)

router = APIRouter(prefix="/api/v1/organizations/{organization_id}/validation")


def _raise(exc: Exception, default_status: int = 400) -> NoReturn:
    status_code = getattr(exc, "status", default_status)
    code = getattr(exc, "code", "validation_error")
    detail = {"code": code, "message": str(exc)}
    raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post(
    "/simulations", response_model=ValidationSimulationRead, status_code=status.HTTP_201_CREATED
)
def create_simulation(
    organization_id: UUID,
    payload: ValidationSimulationCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*VALIDATION_WRITE_ROLES)),
) -> object:
    try:
        return validation_service.create_simulation(
            db,
            organization_id,
            payload.simulation_code,
            payload.name,
            payload.analysis_case_id,
            access.user.user_id,
        )
    except ValidationServiceError as exc:
        _raise(exc)


@router.post(
    "/simulations/{simulation_id}/ground-truth",
    response_model=GroundTruthRead,
    status_code=status.HTTP_201_CREATED,
)
def upload_ground_truth(
    organization_id: UUID,
    simulation_id: UUID,
    payload: GroundTruthUpload,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*VALIDATION_WRITE_ROLES)),
) -> object:
    try:
        return validation_service.upload_ground_truth(
            db,
            organization_id,
            simulation_id,
            payload.model_dump(mode="json"),
            access.user.user_id,
        )
    except ValidationServiceError as exc:
        _raise(exc)


@router.get("/simulations/{simulation_id}", response_model=ValidationSimulationDetail)
def get_simulation(
    organization_id: UUID,
    simulation_id: UUID,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*VALIDATION_READ_ROLES)),
) -> object:
    try:
        simulation = validation_service.get_simulation(db, organization_id, simulation_id)
    except ValidationServiceError as exc:
        _raise(exc)
    versions = validation_service.list_ground_truth_versions(db, organization_id, simulation_id)
    ground_truth_versions = []
    for version in versions:
        expected = validation_ground_truth_repository.list_expected_findings(
            db, organization_id, version.id
        )
        ground_truth_versions.append(
            GroundTruthRead.model_validate(version).model_copy(
                update={"expected_findings": expected}
            )
        )
    return ValidationSimulationDetail(
        **ValidationSimulationRead.model_validate(simulation).model_dump(),
        ground_truth_versions=ground_truth_versions,
    )


@router.post(
    "/simulations/{simulation_id}/validate-run/{analysis_run_id}",
    response_model=ValidationResultRead,
    status_code=status.HTTP_201_CREATED,
)
def validate_run(
    organization_id: UUID,
    simulation_id: UUID,
    analysis_run_id: UUID,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*VALIDATION_WRITE_ROLES)),
) -> object:
    try:
        run, score, matches = validation_service.validate_run(
            db, organization_id, simulation_id, analysis_run_id, access.user.user_id
        )
    except ValidationServiceError as exc:
        _raise(exc)
    return ValidationResultRead(run=run, score=score, matches=matches)


@router.get("/simulations/{simulation_id}/results", response_model=ValidationResultsHistoryRead)
def get_results(
    organization_id: UUID,
    simulation_id: UUID,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*VALIDATION_READ_ROLES)),
) -> object:
    try:
        results = validation_service.get_results(db, organization_id, simulation_id)
    except ValidationServiceError as exc:
        _raise(exc)
    return ValidationResultsHistoryRead(
        simulation_id=simulation_id,
        results=[ValidationResultRead(run=r, score=s, matches=m) for r, s, m in results],
    )
