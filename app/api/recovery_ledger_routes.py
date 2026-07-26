from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.authorization import OrganizationAccess, require_organization_roles
from app.auth.permissions import (
    RECOVERY_FINANCE_ROLES,
    RECOVERY_LEDGER_READ_ROLES,
    RECOVERY_MEASUREMENT_ROLES,
    RECOVERY_WRITE_ROLES,
)
from app.db.session import get_db
from app.schemas.recovery_ledger import (
    CaseCreate,
    CaseRead,
    CaseUpdate,
    ExecutionCreate,
    ExecutionRead,
    FinanceReviewCreate,
    LedgerMutationCreate,
    LedgerPage,
    LedgerRead,
    MeasurementCreate,
    MeasurementRead,
    ValueSummary,
    VerifyCreate,
)
from app.services.recovery_ledger_service import RecoveryLedgerError, recovery_ledger_service

router = APIRouter(prefix="/api/v1/organizations/{organization_id}")


def _raise(exc: RecoveryLedgerError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status, detail={"code": exc.code, "message": str(exc)}
    ) from exc


@router.post("/recovery-cases", response_model=CaseRead, status_code=201)
def create_case(
    organization_id: UUID,
    payload: CaseCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*RECOVERY_WRITE_ROLES)),
) -> object:
    try:
        return recovery_ledger_service.create_case(
            db, organization_id, payload, access.user.user_id
        )
    except RecoveryLedgerError as exc:
        _raise(exc)


@router.get("/recovery-cases", response_model=list[CaseRead])
def list_cases(
    organization_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*RECOVERY_LEDGER_READ_ROLES)),
) -> object:
    return recovery_ledger_service.list_cases(db, organization_id)


@router.get("/recovery-cases/{recovery_case_id}", response_model=CaseRead)
def get_case(
    organization_id: UUID,
    recovery_case_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*RECOVERY_LEDGER_READ_ROLES)),
) -> object:
    try:
        return recovery_ledger_service.get_case(db, organization_id, recovery_case_id)
    except RecoveryLedgerError as exc:
        _raise(exc)


@router.patch("/recovery-cases/{recovery_case_id}", response_model=CaseRead)
def update_case(
    organization_id: UUID,
    recovery_case_id: UUID,
    payload: CaseUpdate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*RECOVERY_WRITE_ROLES)),
) -> object:
    try:
        return recovery_ledger_service.update_case(
            db, organization_id, recovery_case_id, payload, access.user.user_id
        )
    except RecoveryLedgerError as exc:
        _raise(exc)


@router.post(
    "/recovery-cases/{recovery_case_id}/executions", response_model=ExecutionRead, status_code=201
)
def create_execution(
    organization_id: UUID,
    recovery_case_id: UUID,
    payload: ExecutionCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*RECOVERY_WRITE_ROLES)),
) -> object:
    try:
        return recovery_ledger_service.create_execution(
            db, organization_id, recovery_case_id, payload, access.user.user_id
        )
    except RecoveryLedgerError as exc:
        _raise(exc)


def _transition_execution(
    organization_id: UUID,
    execution_id: UUID,
    transition: str,
    db: Session,
    access: OrganizationAccess,
) -> object:
    try:
        return recovery_ledger_service.transition_execution(
            db, organization_id, execution_id, transition, access.user.user_id
        )
    except RecoveryLedgerError as exc:
        _raise(exc)


@router.post("/recovery-executions/{execution_id}/start", response_model=ExecutionRead)
def start_execution(
    organization_id: UUID,
    execution_id: UUID,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*RECOVERY_WRITE_ROLES)),
) -> object:
    return _transition_execution(organization_id, execution_id, "start", db, access)


@router.post("/recovery-executions/{execution_id}/complete", response_model=ExecutionRead)
def complete_execution(
    organization_id: UUID,
    execution_id: UUID,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*RECOVERY_WRITE_ROLES)),
) -> object:
    return _transition_execution(organization_id, execution_id, "complete", db, access)


@router.post(
    "/recovery-executions/{execution_id}/measurements",
    response_model=MeasurementRead,
    status_code=201,
)
def create_measurement(
    organization_id: UUID,
    execution_id: UUID,
    payload: MeasurementCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*RECOVERY_MEASUREMENT_ROLES)),
) -> object:
    try:
        return recovery_ledger_service.create_measurement(
            db, organization_id, execution_id, payload, access.user.user_id
        )
    except RecoveryLedgerError as exc:
        _raise(exc)


@router.get(
    "/recovery-executions/{execution_id}/measurements", response_model=list[MeasurementRead]
)
def list_measurements(
    organization_id: UUID,
    execution_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*RECOVERY_LEDGER_READ_ROLES)),
) -> object:
    try:
        return recovery_ledger_service.list_measurements(db, organization_id, execution_id)
    except RecoveryLedgerError as exc:
        _raise(exc)


@router.post("/recovery-measurements/{measurement_id}/submit", response_model=MeasurementRead)
def submit_measurement(
    organization_id: UUID,
    measurement_id: UUID,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*RECOVERY_MEASUREMENT_ROLES)),
) -> object:
    try:
        return recovery_ledger_service.submit_measurement(
            db, organization_id, measurement_id, access.user.user_id
        )
    except RecoveryLedgerError as exc:
        _raise(exc)


@router.post(
    "/recovery-measurements/{measurement_id}/finance-review", response_model=MeasurementRead
)
def finance_review(
    organization_id: UUID,
    measurement_id: UUID,
    payload: FinanceReviewCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*RECOVERY_FINANCE_ROLES)),
) -> object:
    try:
        return recovery_ledger_service.finance_review(
            db, organization_id, measurement_id, payload, access.user.user_id
        )
    except RecoveryLedgerError as exc:
        _raise(exc)


@router.post(
    "/recovery-measurements/{measurement_id}/verify", response_model=LedgerRead, status_code=201
)
def verify(
    organization_id: UUID,
    measurement_id: UUID,
    payload: VerifyCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*RECOVERY_FINANCE_ROLES)),
) -> object:
    try:
        return recovery_ledger_service.verify(
            db, organization_id, measurement_id, payload, access.user.user_id
        )
    except RecoveryLedgerError as exc:
        _raise(exc)


@router.get("/verified-value-ledger", response_model=LedgerPage)
def list_ledger(
    organization_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    recovery_case_id: UUID | None = None,
    currency: str | None = Query(None, pattern=r"^[A-Z]{3}$"),
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*RECOVERY_LEDGER_READ_ROLES)),
) -> LedgerPage:
    rows, total = recovery_ledger_service.list_ledger(
        db, organization_id, page, page_size, recovery_case_id, currency
    )
    return LedgerPage(items=rows, page=page, page_size=page_size, total=total)


@router.get("/verified-value-ledger/{ledger_entry_id}", response_model=LedgerRead)
def get_ledger(
    organization_id: UUID,
    ledger_entry_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*RECOVERY_LEDGER_READ_ROLES)),
) -> object:
    try:
        return recovery_ledger_service.get_ledger(db, organization_id, ledger_entry_id)
    except RecoveryLedgerError as exc:
        _raise(exc)


@router.post(
    "/verified-value-ledger/{ledger_entry_id}/adjustments",
    response_model=LedgerRead,
    status_code=201,
)
def adjustment(
    organization_id: UUID,
    ledger_entry_id: UUID,
    payload: LedgerMutationCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*RECOVERY_FINANCE_ROLES)),
) -> object:
    try:
        return recovery_ledger_service.adjustment(
            db, organization_id, ledger_entry_id, payload, access.user.user_id
        )
    except RecoveryLedgerError as exc:
        _raise(exc)


@router.post(
    "/verified-value-ledger/{ledger_entry_id}/reversals", response_model=LedgerRead, status_code=201
)
def reversal(
    organization_id: UUID,
    ledger_entry_id: UUID,
    payload: LedgerMutationCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*RECOVERY_FINANCE_ROLES)),
) -> object:
    try:
        return recovery_ledger_service.reversal(
            db, organization_id, ledger_entry_id, payload, access.user.user_id
        )
    except RecoveryLedgerError as exc:
        _raise(exc)


@router.get("/recovery-cases/{recovery_case_id}/value-summary", response_model=ValueSummary)
def summary(
    organization_id: UUID,
    recovery_case_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*RECOVERY_LEDGER_READ_ROLES)),
) -> object:
    try:
        return recovery_ledger_service.summary(db, organization_id, recovery_case_id)
    except RecoveryLedgerError as exc:
        _raise(exc)


@router.get("/recovery-cases/{recovery_case_id}/ledger", response_model=LedgerPage)
def case_ledger(
    organization_id: UUID,
    recovery_case_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*RECOVERY_LEDGER_READ_ROLES)),
) -> LedgerPage:
    rows, total = recovery_ledger_service.list_ledger(
        db, organization_id, page, page_size, recovery_case_id
    )
    return LedgerPage(items=rows, page=page, page_size=page_size, total=total)
