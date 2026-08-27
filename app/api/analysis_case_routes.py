from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.auth.authorization import OrganizationAccess, require_organization_roles
from app.auth.permissions import (
    ANALYSIS_CASE_ADMIN_ROLES,
    ANALYSIS_CASE_CREATE_ROLES,
    ANALYSIS_CASE_READ_ROLES,
)
from app.db.session import SessionLocal, get_db
from app.models.analysis_case import AnalysisCaseRunStatus
from app.schemas.analysis_case import (
    AnalysisCaseActionCreate,
    AnalysisCaseActionRead,
    AnalysisCaseActionStatusUpdate,
    AnalysisCaseCreate,
    AnalysisCaseDatasetRead,
    AnalysisCaseFindingRead,
    AnalysisCaseRead,
    AnalysisCaseRecoveryRead,
    AnalysisCaseRecoveryUpsert,
    AnalysisCaseRunRead,
)
from app.services.analysis_case_action_service import (
    AnalysisCaseActionServiceError,
    analysis_case_action_service,
)
from app.services.analysis_case_command_service import analysis_case_command_service
from app.services.analysis_case_orchestration_service import (
    AnalysisCaseOrchestrationError,
    analysis_case_orchestration_service,
)
from app.services.analysis_case_recovery_service import (
    AnalysisCaseRecoveryServiceError,
    analysis_case_recovery_service,
)
from app.services.analysis_case_service import (
    AnalysisCaseServiceError,
    UploadedFile,
    analysis_case_service,
)

router = APIRouter(prefix="/api/v1/organizations/{organization_id}/analysis-cases")


def _raise(exc: Exception, default_status: int = 400) -> NoReturn:
    status_code = getattr(exc, "status", default_status)
    code = getattr(exc, "code", "analysis_case_error")
    detail = {"code": code, "message": str(exc)}
    raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("", response_model=AnalysisCaseRead, status_code=status.HTTP_201_CREATED)
def create_case(
    organization_id: UUID,
    payload: AnalysisCaseCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ANALYSIS_CASE_CREATE_ROLES)),
) -> object:
    try:
        return analysis_case_service.create(
            db,
            organization_id,
            payload.name,
            payload.mode.value,
            access.user.user_id,
            industry_code=payload.industry_code,
            business_model=payload.business_model,
            operating_context=payload.operating_context,
            case_currency_hint=payload.case_currency_hint,
            idempotency_key=payload.idempotency_key,
        )
    except AnalysisCaseServiceError as exc:
        _raise(exc)


@router.get("", response_model=list[AnalysisCaseRead])
def list_cases(
    organization_id: UUID,
    include_archived: bool = False,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*ANALYSIS_CASE_READ_ROLES)),
) -> object:
    return analysis_case_service.list_cases(db, organization_id, include_archived=include_archived)


@router.get("/{case_id}", response_model=AnalysisCaseRead)
def get_case(
    organization_id: UUID,
    case_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*ANALYSIS_CASE_READ_ROLES)),
) -> object:
    try:
        return analysis_case_service.get(db, organization_id, case_id)
    except AnalysisCaseServiceError as exc:
        _raise(exc)


@router.post("/{case_id}/archive", response_model=AnalysisCaseRead)
def archive_case(
    organization_id: UUID,
    case_id: UUID,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ANALYSIS_CASE_ADMIN_ROLES)),
) -> object:
    """Soft-archive only -- hides the case from the default list view.
    Never deletes it or anything it produced; GET /{case_id} and every
    nested route keep working unchanged for an archived case."""
    try:
        return analysis_case_service.archive(db, organization_id, case_id, access.user.user_id)
    except AnalysisCaseServiceError as exc:
        _raise(exc)


@router.post("/{case_id}/artifacts", status_code=status.HTTP_201_CREATED)
async def upload_artifacts(
    organization_id: UUID,
    case_id: UUID,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ANALYSIS_CASE_CREATE_ROLES)),
) -> object:
    try:
        uploaded = [
            UploadedFile(filename=f.filename or "upload", content=await f.read()) for f in files
        ]
        artifacts = analysis_case_service.register_artifacts(
            db, organization_id, case_id, uploaded, access.user.user_id
        )
    except AnalysisCaseServiceError as exc:
        _raise(exc)
    return [
        {
            "id": str(a.id),
            "original_filename": a.original_filename,
            "mime_type": a.mime_type,
            "size_bytes": a.size_bytes,
            "parser_status": a.parser_status,
            "extraction_status": a.extraction_status,
        }
        for a in artifacts
    ]


@router.get("/{case_id}/datasets", response_model=list[AnalysisCaseDatasetRead])
def list_datasets(
    organization_id: UUID,
    case_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*ANALYSIS_CASE_READ_ROLES)),
) -> object:
    return analysis_case_service.list_datasets(db, organization_id, case_id)


def _execute_run_in_background(
    organization_id: UUID, case_id: UUID, run_id: UUID, actor_user_id: UUID
) -> None:
    """Runs after the HTTP response has already been sent (FastAPI
    BackgroundTasks) -- survives browser disconnect/HTTP timeout, per the
    plan's async-execution decision. Uses its own DB session since the
    request-scoped session is closed by the time this runs."""
    with SessionLocal() as background_db:
        analysis_case_orchestration_service.execute(
            background_db,
            analysis_case_service.storage,
            organization_id,
            case_id,
            run_id,
            actor_user_id,
        )


@router.post(
    "/{case_id}/run", response_model=AnalysisCaseRunRead, status_code=status.HTTP_202_ACCEPTED
)
def run_case(
    organization_id: UUID,
    case_id: UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ANALYSIS_CASE_CREATE_ROLES)),
) -> object:
    try:
        run = analysis_case_orchestration_service.start_run(
            db, organization_id, case_id, access.user.user_id
        )
    except AnalysisCaseOrchestrationError as exc:
        _raise(exc)
    background_tasks.add_task(
        _execute_run_in_background, organization_id, case_id, run.id, access.user.user_id
    )
    return run


@router.get("/{case_id}/runs", response_model=list[AnalysisCaseRunRead])
def list_runs(
    organization_id: UUID,
    case_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*ANALYSIS_CASE_READ_ROLES)),
) -> object:
    from sqlalchemy import select

    from app.models.analysis_case import AnalysisCaseRun

    return list(
        db.scalars(
            select(AnalysisCaseRun)
            .where(
                AnalysisCaseRun.organization_id == organization_id,
                AnalysisCaseRun.analysis_case_id == case_id,
            )
            .order_by(AnalysisCaseRun.run_number.desc())
        ).all()
    )


@router.get("/{case_id}/runs/{run_id}/status", response_model=AnalysisCaseRunRead)
def get_run_status(
    organization_id: UUID,
    case_id: UUID,
    run_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*ANALYSIS_CASE_READ_ROLES)),
) -> object:
    from app.models.analysis_case import AnalysisCaseRun

    run = db.get(AnalysisCaseRun, run_id)
    if run is None or run.organization_id != organization_id or run.analysis_case_id != case_id:
        raise HTTPException(
            status_code=404, detail={"code": "run_not_found", "message": "Run not found"}
        )
    if run.status == AnalysisCaseRunStatus.RUNNING.value:
        from app.core.config import get_settings

        analysis_case_orchestration_service.mark_stale_if_needed(
            db, run, get_settings().run_stale_after_seconds
        )
    return run


@router.get("/{case_id}/findings", response_model=list[AnalysisCaseFindingRead])
def list_findings(
    organization_id: UUID,
    case_id: UUID,
    run_id: UUID | None = None,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*ANALYSIS_CASE_READ_ROLES)),
) -> object:
    prioritized = analysis_case_command_service.priorities(db, organization_id, case_id, run_id)
    return [
        {
            "finding_id": p.finding.id,
            "rule_id": p.finding.rule_id,
            "title": p.finding.title,
            "summary": p.finding.summary,
            "severity": p.finding.severity,
            "confidence_level": p.finding.confidence_level,
            "affected_record_count": p.finding.affected_record_count,
            "economic_status": p.finding.economic_status,
            "currency_status": p.finding.currency_status,
            "entities": p.finding.entities_json,
            "domains": p.finding.domains_json,
            "observed_values_by_currency": p.observed_values_by_currency,
        }
        for p in prioritized
    ]


@router.get("/{case_id}/command/priorities", response_model=list[AnalysisCaseFindingRead])
def command_priorities(
    organization_id: UUID,
    case_id: UUID,
    run_id: UUID | None = None,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*ANALYSIS_CASE_READ_ROLES)),
) -> object:
    return list_findings(organization_id, case_id, run_id, db, _)


@router.post(
    "/{case_id}/actions", response_model=AnalysisCaseActionRead, status_code=status.HTTP_201_CREATED
)
def create_action(
    organization_id: UUID,
    case_id: UUID,
    payload: AnalysisCaseActionCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ANALYSIS_CASE_CREATE_ROLES)),
) -> object:
    try:
        return analysis_case_action_service.create(
            db,
            organization_id,
            case_id,
            payload.finding_ids,
            payload.title,
            payload.description,
            payload.owner,
            payload.priority,
            payload.due_date,
            access.user.user_id,
        )
    except AnalysisCaseActionServiceError as exc:
        _raise(exc)


@router.get("/{case_id}/actions", response_model=list[AnalysisCaseActionRead])
def list_actions(
    organization_id: UUID,
    case_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*ANALYSIS_CASE_READ_ROLES)),
) -> object:
    return analysis_case_action_service.list(db, organization_id, case_id)


@router.patch("/{case_id}/actions/{action_id}", response_model=AnalysisCaseActionRead)
def update_action(
    organization_id: UUID,
    case_id: UUID,
    action_id: UUID,
    payload: AnalysisCaseActionStatusUpdate,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*ANALYSIS_CASE_CREATE_ROLES)),
) -> object:
    try:
        return analysis_case_action_service.update_status(
            db, organization_id, action_id, payload.status.value, payload.owner
        )
    except AnalysisCaseActionServiceError as exc:
        _raise(exc)


@router.post(
    "/{case_id}/actions/{action_id}/recovery",
    response_model=AnalysisCaseRecoveryRead,
    status_code=status.HTTP_200_OK,
)
def upsert_recovery(
    organization_id: UUID,
    case_id: UUID,
    action_id: UUID,
    payload: AnalysisCaseRecoveryUpsert,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*ANALYSIS_CASE_ADMIN_ROLES)),
) -> object:
    try:
        return analysis_case_recovery_service.upsert(
            db,
            organization_id,
            case_id,
            action_id,
            payload.finding_id,
            payload.baseline_condition,
            payload.intervention_summary,
            payload.recovery_status.value,
            payload.observed_post_condition,
            payload.observed_value,
            payload.estimated_value,
            payload.verified_value,
            payload.currency_detail,
            payload.evidence_json,
        )
    except AnalysisCaseRecoveryServiceError as exc:
        _raise(exc)


@router.get(
    "/{case_id}/actions/{action_id}/recovery", response_model=AnalysisCaseRecoveryRead | None
)
def get_recovery(
    organization_id: UUID,
    case_id: UUID,
    action_id: UUID,
    finding_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*ANALYSIS_CASE_READ_ROLES)),
) -> object:
    return analysis_case_recovery_service.get(db, organization_id, action_id, finding_id)
