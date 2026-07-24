from io import BytesIO

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.engines.trust_engine import TrustEngine
from app.rules.maintenance_rules import detect_repeated_asset_failures
from app.schemas.contracts import FindingRead, RecoveryActionCreate, RecoveryActionRead, TrustReport
from app.services.finding_service import FindingService
from app.services.recovery_service import RecoveryService

router = APIRouter(prefix="/api/v1")
trust_engine = TrustEngine()
finding_service = FindingService()
recovery_service = RecoveryService()


async def _read_tabular(file: UploadFile) -> pd.DataFrame:
    content = await file.read()
    name = file.filename or "upload"
    if name.lower().endswith(".csv"):
        return pd.read_csv(BytesIO(content))
    if name.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(BytesIO(content))
    raise HTTPException(status_code=400, detail="Only CSV and Excel files are supported")


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "platform": "Intel4Ops Core", "phase": 2}


@router.post("/trust/profile", response_model=TrustReport)
async def trust_profile(file: UploadFile = File(...)) -> TrustReport:
    dataframe = await _read_tabular(file)
    return trust_engine.profile(dataframe, file.filename or "upload")


@router.post("/intelligence/maintenance/analyze", response_model=list[FindingRead])
async def analyze_maintenance(
    file: UploadFile = File(...), db: Session = Depends(get_db)
) -> list[FindingRead]:
    dataframe = await _read_tabular(file)
    try:
        payloads = detect_repeated_asset_failures(dataframe)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return [finding_service.create(db, payload) for payload in payloads]


@router.get("/command/findings", response_model=list[FindingRead])
def list_findings(db: Session = Depends(get_db)) -> list[FindingRead]:
    return finding_service.list(db)


@router.post("/recovery/actions", response_model=RecoveryActionRead)
def create_recovery_action(
    payload: RecoveryActionCreate, db: Session = Depends(get_db)
) -> RecoveryActionRead:
    try:
        return recovery_service.create(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
