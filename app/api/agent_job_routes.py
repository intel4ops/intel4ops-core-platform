"""AGENTIC-CONTROL-001 Phase E: HTTP surface for the Agent Job Queue.

Two distinct auth surfaces on purpose (Phase N): `/agent-jobs*` endpoints
that a human/organization session uses (create, list, approve) require
`OrganizationAccess`; `/agent-jobs/claim` and its callbacks that a Local
Worker Bridge uses require a scoped `AgentWorkerCredential` instead. A
worker credential can never reach the human-session endpoints and vice
versa.
"""

from __future__ import annotations

from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.authorization import OrganizationAccess, require_organization_roles
from app.auth.permissions import (
    AGENT_JOB_CREATE_ROLES,
    AGENT_JOB_OWNER_APPROVAL_ROLES,
    AGENT_JOB_READ_ROLES,
    AGENT_WORKER_CREDENTIAL_ADMIN_ROLES,
)
from app.auth.worker_auth import generate_worker_token, hash_worker_token, require_worker_credential
from app.core.config import get_settings
from app.db.session import get_db
from app.models.agent_jobs import AgentJobRiskClass, AgentWorkerCredential
from app.schemas.agent_jobs import (
    AgentJobClaimResponse,
    AgentJobCreate,
    AgentJobFailureSubmit,
    AgentJobHeartbeatRequest,
    AgentJobRead,
    AgentJobResultSubmit,
    OwnerApprovalDecision,
)
from app.services.agent_job_service import AgentJobLeaseLost, AgentJobService, AgentJobServiceError
from app.services.agent_routing_service import agent_routing_policy
from app.storage.local_storage import LocalFileStorage

router = APIRouter(prefix="/api/v1/organizations/{organization_id}/agent-jobs")


def _raise(exc: Exception, default_status: int = 400) -> NoReturn:
    if isinstance(exc, AgentJobServiceError):
        raise HTTPException(
            status_code=exc.status, detail={"code": exc.code, "message": str(exc)}
        ) from exc
    raise HTTPException(status_code=default_status, detail=str(exc)) from exc


def _service() -> AgentJobService:
    return AgentJobService(storage=LocalFileStorage(get_settings().storage_root))


@router.post("", response_model=AgentJobRead, status_code=201)
def create_agent_job(
    organization_id: UUID,
    payload: AgentJobCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*AGENT_JOB_CREATE_ROLES)),
) -> object:
    try:
        return _service().create_job(db, organization_id, payload, access.user.user_id)
    except AgentJobServiceError as exc:
        _raise(exc)


@router.get("/{job_id}", response_model=AgentJobRead)
def get_agent_job(
    organization_id: UUID,
    job_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*AGENT_JOB_READ_ROLES)),
) -> object:
    try:
        return _service().get(db, organization_id, job_id)
    except AgentJobServiceError as exc:
        _raise(exc)


@router.post("/{job_id}/owner-decision", response_model=AgentJobRead)
def decide_agent_job(
    organization_id: UUID,
    job_id: UUID,
    payload: OwnerApprovalDecision,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*AGENT_JOB_OWNER_APPROVAL_ROLES)),
) -> object:
    service = _service()
    try:
        job = service.get(db, organization_id, job_id)
        return service.apply_owner_decision(db, job, payload.approve, payload.note)
    except AgentJobServiceError as exc:
        _raise(exc)


@router.post("/worker-credentials", status_code=201)
def create_worker_credential(
    organization_id: UUID,
    worker_id: str,
    allowed_job_types: list[str] | None = None,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(
        require_organization_roles(*AGENT_WORKER_CREDENTIAL_ADMIN_ROLES)
    ),
) -> dict:
    """Issues a scoped, R0/R1-only worker credential. The raw token is
    returned exactly once here and is never recoverable again -- only its
    hash is persisted (Phase N)."""
    token = generate_worker_token()
    credential = AgentWorkerCredential(
        organization_id=organization_id,
        worker_id=worker_id,
        token_hash=hash_worker_token(token),
        allowed_risk_classes=[AgentJobRiskClass.R0.value, AgentJobRiskClass.R1.value],
        allowed_job_types=allowed_job_types,
    )
    db.add(credential)
    db.commit()
    return {"worker_id": worker_id, "token": token}


@router.post("/claim", response_model=AgentJobClaimResponse | None)
def claim_agent_job(
    organization_id: UUID,
    db: Session = Depends(get_db),
    credential: AgentWorkerCredential = Depends(require_worker_credential),
) -> object:
    from datetime import timedelta

    service = _service()
    # Opportunistic stale-lease recovery (Phase O) -- mirrors
    # MappingExecutionWorker.run()'s recover_stale_once() call, but
    # invoked on every claim request rather than needing a separate
    # scheduled process, since AgentJob workers are remote/pull-based and
    # there is no long-lived in-process worker loop on the server side to
    # host a periodic sweep.
    service.recover_stale(db, timedelta(seconds=get_settings().agent_job_stale_threshold_seconds))
    claim = service.claim_next(db, credential)
    if claim is None:
        return None
    job = service.get(db, organization_id, claim.job_id)
    evidence_package = service.get_evidence_package(job)
    routing = agent_routing_policy.route(job.risk_class)
    model_params = agent_routing_policy.model_parameters(routing.worker_profile)
    return AgentJobClaimResponse(
        job=job,
        lease_id=claim.lease_id,
        evidence_package=evidence_package,
        model_profile=routing.worker_profile.value,
        model_identifier=str(model_params.get("model", "")),
        model_parameters=model_params,
    )


@router.post("/{job_id}/heartbeat", status_code=204)
def heartbeat_agent_job(
    organization_id: UUID,
    job_id: UUID,
    payload: AgentJobHeartbeatRequest,
    db: Session = Depends(get_db),
    credential: AgentWorkerCredential = Depends(require_worker_credential),
) -> None:
    from app.services.agent_job_service import AgentJobClaim

    service = _service()
    ok = service.heartbeat(
        db, AgentJobClaim(job_id, organization_id, payload.lease_id, credential.worker_id)
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Lease is no longer valid")


@router.post("/{job_id}/result", response_model=AgentJobRead)
def submit_agent_job_result(
    organization_id: UUID,
    job_id: UUID,
    payload: AgentJobResultSubmit,
    db: Session = Depends(get_db),
    credential: AgentWorkerCredential = Depends(require_worker_credential),
) -> object:
    from app.services.agent_job_service import AgentJobClaim

    service = _service()
    claim = AgentJobClaim(job_id, organization_id, payload.lease_id, credential.worker_id)
    try:
        return service.submit_result(
            db,
            claim,
            payload.structured_result.model_dump(mode="json"),
            payload.execution_time_ms,
            payload.input_tokens,
            payload.output_tokens,
            payload.reasoning_tokens,
            payload.model_identifier,
        )
    except AgentJobLeaseLost as exc:
        raise HTTPException(status_code=409, detail="Lease is no longer valid") from exc


@router.post("/{job_id}/failure", response_model=AgentJobRead)
def submit_agent_job_failure(
    organization_id: UUID,
    job_id: UUID,
    payload: AgentJobFailureSubmit,
    db: Session = Depends(get_db),
    credential: AgentWorkerCredential = Depends(require_worker_credential),
) -> object:
    from app.services.agent_job_service import AgentJobClaim

    service = _service()
    claim = AgentJobClaim(job_id, organization_id, payload.lease_id, credential.worker_id)
    try:
        return service.submit_failure(
            db, claim, payload.error_code, payload.error_detail, payload.retryable
        )
    except AgentJobLeaseLost as exc:
        raise HTTPException(status_code=409, detail="Lease is no longer valid") from exc
