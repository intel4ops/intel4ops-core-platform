from io import BytesIO
from uuid import UUID

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.auth.authorization import (
    OrganizationAccess,
    require_organization_roles,
    require_platform_admin,
)
from app.auth.identity import AuthenticatedUser
from app.auth.permissions import (
    MAINTENANCE_ANALYSIS_ROLES,
    ORGANIZATION_ADMIN_ROLES,
    ORGANIZATION_READ_ROLES,
    RECOVERY_WRITE_ROLES,
)
from app.db.session import get_db
from app.engines.trust_engine import TrustEngine
from app.models.entities import Finding, Organization, RecoveryAction
from app.rules.maintenance_rules import detect_repeated_asset_failures
from app.schemas.contracts import (
    FindingRead,
    OrganizationCreate,
    OrganizationRead,
    OrganizationUpdate,
    RecoveryActionCreate,
    RecoveryActionRead,
    TrustReport,
)
from app.services.finding_service import FindingService
from app.services.organization_service import (
    DuplicateOrganizationSlugError,
    OrganizationNotFoundError,
    OrganizationService,
)
from app.services.recovery_service import RecoveryService

router = APIRouter(prefix="/api/v1")
trust_engine = TrustEngine()
finding_service = FindingService()
recovery_service = RecoveryService()
organization_service = OrganizationService()


async def _read_tabular(file: UploadFile) -> pd.DataFrame:
    content = await file.read()
    name = file.filename or "upload"
    if name.lower().endswith(".csv"):
        return pd.read_csv(BytesIO(content))
    if name.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(BytesIO(content))
    raise HTTPException(status_code=400, detail="Only CSV and Excel files are supported")


@router.get("/health")
def health() -> dict[str, object]:
    return {"status": "ok", "platform": "Intel4Ops Core", "phase": 2}


@router.post("/organizations", response_model=OrganizationRead, status_code=201)
def create_organization(
    payload: OrganizationCreate,
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_platform_admin),
) -> Organization:
    try:
        return organization_service.create(db, payload)
    except DuplicateOrganizationSlugError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/organizations", response_model=list[OrganizationRead])
def list_organizations(
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_platform_admin),
) -> list[Organization]:
    return organization_service.list(db)


@router.get("/organizations/{organization_id}", response_model=OrganizationRead)
def get_organization(
    organization_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*ORGANIZATION_READ_ROLES)),
) -> Organization:
    try:
        return organization_service.get(db, organization_id)
    except OrganizationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/organizations/{organization_id}", response_model=OrganizationRead)
def update_organization(
    organization_id: UUID,
    payload: OrganizationUpdate,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*ORGANIZATION_ADMIN_ROLES)),
) -> Organization:
    try:
        return organization_service.update(db, organization_id, payload)
    except OrganizationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DuplicateOrganizationSlugError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/organizations/{organization_id}/deactivate", response_model=OrganizationRead)
def deactivate_organization(
    organization_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*ORGANIZATION_ADMIN_ROLES)),
) -> Organization:
    try:
        return organization_service.deactivate(db, organization_id)
    except OrganizationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/trust/profile", response_model=TrustReport)
async def trust_profile(file: UploadFile = File(...)) -> TrustReport:
    dataframe = await _read_tabular(file)
    return trust_engine.profile(dataframe, file.filename or "upload")


@router.post(
    "/intelligence/maintenance/analyze",
    response_model=list[FindingRead],
    include_in_schema=False,
)
async def analyze_maintenance(
    organization_id: UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*MAINTENANCE_ANALYSIS_ROLES)),
) -> list[Finding]:
    dataframe = await _read_tabular(file)
    try:
        payloads = detect_repeated_asset_failures(dataframe)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        return [finding_service.create(db, organization_id, payload) for payload in payloads]
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/command/findings",
    response_model=list[FindingRead],
    include_in_schema=False,
)
def list_findings(
    organization_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*ORGANIZATION_READ_ROLES)),
) -> list[Finding]:
    return finding_service.list(db, organization_id)


@router.post(
    "/recovery/actions",
    response_model=RecoveryActionRead,
    include_in_schema=False,
)
def create_recovery_action(
    organization_id: UUID,
    payload: RecoveryActionCreate,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*RECOVERY_WRITE_ROLES)),
) -> RecoveryAction:
    try:
        return recovery_service.create(db, organization_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
