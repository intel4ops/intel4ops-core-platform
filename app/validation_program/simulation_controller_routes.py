from __future__ import annotations

from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.authorization import OrganizationAccess, require_organization_roles
from app.auth.permissions import ORGANIZATION_ADMIN_ROLES
from app.core.config import get_settings
from app.db.session import get_db
from app.models.simulation_batch import SimulationBatch, SimulationBatchItem, SimulationBatchStatus
from app.storage.local_storage import LocalFileStorage
from app.validation_program.autonomous_engineering_handoff import (
    AutonomousEngineeringHandoffError,
    AutonomousEngineeringHandoffService,
)
from app.validation_program.batch_controller import (
    SimulationBatchController,
    SimulationControllerError,
    TruthIsolationViolation,
)
from app.validation_program.simulation_package_staging import (
    SimulationPackageStagingError,
    SimulationPackageStagingService,
)

router = APIRouter(prefix="/api/v1/organizations/{organization_id}/simulation-controller")


def _raise(exc: Exception, default_status: int = 400) -> NoReturn:
    status_code = getattr(exc, "status", default_status)
    code = getattr(exc, "code", "simulation_controller_error")
    raise HTTPException(
        status_code=status_code, detail={"code": code, "message": str(exc)}
    ) from exc


def _controller() -> SimulationBatchController:
    settings = get_settings()
    return SimulationBatchController(LocalFileStorage(settings.storage_root))


def _staging_service() -> SimulationPackageStagingService:
    settings = get_settings()
    return SimulationPackageStagingService(
        settings.storage_root, settings.max_case_total_size_bytes
    )


def _handoff_service() -> AutonomousEngineeringHandoffService:
    settings = get_settings()
    return AutonomousEngineeringHandoffService(LocalFileStorage(settings.storage_root))


def _get_batch(db: Session, organization_id: UUID, batch_id: UUID) -> SimulationBatch:
    batch = db.scalar(
        select(SimulationBatch).where(
            SimulationBatch.id == batch_id,
            SimulationBatch.organization_id == organization_id,
        )
    )
    if batch is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "BATCH_NOT_FOUND", "message": "Simulation batch not found"},
        )
    return batch


def _batch_payload(db: Session, batch: SimulationBatch) -> dict[str, object]:
    items = list(
        db.scalars(
            select(SimulationBatchItem)
            .where(SimulationBatchItem.batch_id == batch.id)
            .order_by(SimulationBatchItem.created_at, SimulationBatchItem.id)
        )
    )
    return {
        "id": batch.id,
        "organization_id": batch.organization_id,
        "name": batch.name,
        "status": batch.status,
        "safety_gate_reason": batch.safety_gate_reason,
        "decision_package_ref": batch.decision_package_ref,
        "created_at": batch.created_at,
        "items": [
            {
                "id": item.id,
                "simulation_id": item.simulation_id,
                "state": item.state,
                "analysis_case_id": item.analysis_case_id,
                "run_id": item.run_id,
                "validation_simulation_id": item.validation_simulation_id,
                "frozen_at": item.frozen_at,
                "truth_accessed_at": item.truth_accessed_at,
                "scored_at": item.scored_at,
                "true_positive_count": item.true_positive_count,
                "false_positive_count": item.false_positive_count,
                "false_negative_count": item.false_negative_count,
                "precision": item.precision,
                "recall": item.recall,
                "economic_capture_value": item.economic_capture_value,
                "economic_total_value": item.economic_total_value,
                "currency": item.currency,
                "block_reason": item.block_reason,
            }
            for item in items
        ],
    }


@router.post("/batches/stage", status_code=status.HTTP_201_CREATED)
def stage_one_simulation(
    organization_id: UUID,
    name: str = Form(min_length=1, max_length=200),
    package: UploadFile = File(...),
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ORGANIZATION_ADMIN_ROLES)),
) -> dict[str, object]:
    staging = _staging_service()
    try:
        staged = staging.stage_zip(organization_id, package.file)
        try:
            batch = _controller().select_batch(
                db,
                organization_id,
                staged.corpus_root,
                access.user.user_id,
                name,
                batch_size=1,
            )
        except Exception:
            staging.discard_staged(staged.corpus_root)
            raise
        try:
            staging.finalize_for_batch(organization_id, batch.id, staged.corpus_root)
        except Exception as exc:
            batch.status = SimulationBatchStatus.PAUSED_SAFETY_GATE.value
            batch.safety_gate_reason = f"package staging finalization failed: {exc}"
            db.commit()
            raise
        return _batch_payload(db, batch)
    except (SimulationPackageStagingError, SimulationControllerError) as exc:
        _raise(exc)


@router.get("/batches/{batch_id}")
def get_simulation_batch(
    organization_id: UUID,
    batch_id: UUID,
    db: Session = Depends(get_db),
    _access: OrganizationAccess = Depends(require_organization_roles(*ORGANIZATION_ADMIN_ROLES)),
) -> dict[str, object]:
    return _batch_payload(db, _get_batch(db, organization_id, batch_id))


@router.post("/batches/{batch_id}/prepare")
def prepare_simulation_batch(
    organization_id: UUID,
    batch_id: UUID,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ORGANIZATION_ADMIN_ROLES)),
) -> dict[str, object]:
    batch = _get_batch(db, organization_id, batch_id)
    corpus_root = _staging_service().batch_corpus_root(organization_id, batch_id)
    if not corpus_root.is_dir():
        raise HTTPException(
            status_code=409,
            detail={
                "code": "PACKAGE_NOT_STAGED",
                "message": "No staged simulation package exists for this batch",
            },
        )
    try:
        _controller().prepare_batch(db, batch_id, corpus_root, access.user.user_id)
    except (SimulationControllerError, TruthIsolationViolation) as exc:
        _raise(exc)
    db.refresh(batch)
    return _batch_payload(db, batch)


@router.post("/batches/{batch_id}/run")
def run_simulation_batch(
    organization_id: UUID,
    batch_id: UUID,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ORGANIZATION_ADMIN_ROLES)),
) -> dict[str, object]:
    batch = _get_batch(db, organization_id, batch_id)
    try:
        _controller().run_batch(db, batch_id, access.user.user_id)
    except (SimulationControllerError, TruthIsolationViolation) as exc:
        _raise(exc)
    db.refresh(batch)
    return _batch_payload(db, batch)


@router.post("/batches/{batch_id}/classify-misses")
def create_miss_classification_jobs(
    organization_id: UUID,
    batch_id: UUID,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ORGANIZATION_ADMIN_ROLES)),
) -> dict[str, object]:
    batch = _get_batch(db, organization_id, batch_id)
    try:
        job_ids = _controller().create_miss_classification_jobs(db, batch_id, access.user.user_id)
    except (SimulationControllerError, TruthIsolationViolation) as exc:
        _raise(exc)
    db.refresh(batch)
    payload = _batch_payload(db, batch)
    payload["created_agent_job_ids"] = job_ids
    return payload


@router.post("/batches/{batch_id}/engineering-handoff")
def prepare_engineering_handoff(
    organization_id: UUID,
    batch_id: UUID,
    db: Session = Depends(get_db),
    _access: OrganizationAccess = Depends(require_organization_roles(*ORGANIZATION_ADMIN_ROLES)),
) -> dict[str, object]:
    try:
        handoff = _handoff_service().prepare(db, organization_id, batch_id)
    except AutonomousEngineeringHandoffError as exc:
        _raise(exc)
    batch = _get_batch(db, organization_id, batch_id)
    return {
        "batch": _batch_payload(db, batch),
        "decision_package_ref": handoff.decision_package_ref,
        "engineering_handoff_ref": handoff.engineering_handoff_ref,
        "target_worker_profile": "CODEX_IMPLEMENTATION",
        "owner_approval_required": handoff.owner_approval_required,
        "dispatch_allowed": False,
        "status": handoff.status,
    }
