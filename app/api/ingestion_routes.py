from collections.abc import Callable
from datetime import datetime
from typing import NoReturn, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.authorization import OrganizationAccess, require_organization_roles
from app.auth.permissions import (
    INGESTION_ADMIN_ROLES,
    INGESTION_OPERATION_ROLES,
    INGESTION_READ_ROLES,
    INGESTION_RELEASE_ROLES,
)
from app.db.session import get_db
from app.models.ingestion import (
    Dataset,
    DatasetStatus,
    DatasetType,
    DatasetVersion,
    DatasetVersionStatus,
    IngestionBatch,
    IngestionBatchStatus,
    IngestionMethod,
    SchemaStatus,
    TriggerType,
)
from app.models.source_system import DataClassification
from app.schemas.ingestion import (
    BatchCountsUpdate,
    BatchFailure,
    BatchTransition,
    DatasetCreate,
    DatasetRead,
    DatasetUpdate,
    DatasetVersionCountsUpdate,
    DatasetVersionCreate,
    DatasetVersionRead,
    DatasetVersionTransition,
    IngestionBatchCreate,
    IngestionBatchRead,
)
from app.services.ingestion_service import (
    IngestionConflictError,
    IngestionNotFoundError,
    IngestionTenantMismatchError,
    InvalidIngestionTransitionError,
    dataset_service,
    dataset_version_service,
    ingestion_batch_service,
)

router = APIRouter(prefix="/api/v1/organizations/{organization_id}")


def _translate_error(exc: Exception) -> NoReturn:
    if isinstance(
        exc,
        (
            IngestionConflictError,
            IngestionTenantMismatchError,
            InvalidIngestionTransitionError,
        ),
    ):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/ingestion-batches",
    response_model=IngestionBatchRead,
    status_code=status.HTTP_201_CREATED,
)
def create_batch(
    organization_id: UUID,
    payload: IngestionBatchCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*INGESTION_OPERATION_ROLES)),
) -> IngestionBatch:
    try:
        return ingestion_batch_service.create(db, organization_id, payload, access.user.user_id)
    except (IngestionConflictError, IngestionTenantMismatchError) as exc:
        _translate_error(exc)


@router.get("/ingestion-batches", response_model=list[IngestionBatchRead])
def list_batches(
    organization_id: UUID,
    source_system_id: UUID | None = None,
    batch_status: IngestionBatchStatus | None = Query(default=None, alias="status"),
    ingestion_method: IngestionMethod | None = None,
    trigger_type: TriggerType | None = None,
    received_from: datetime | None = None,
    received_to: datetime | None = None,
    correlation_id: str | None = None,
    external_batch_id: str | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*INGESTION_READ_ROLES)),
) -> list[IngestionBatch]:
    return ingestion_batch_service.list(
        db,
        organization_id,
        source_system_id=source_system_id,
        status=batch_status,
        ingestion_method=ingestion_method,
        trigger_type=trigger_type,
        received_from=received_from,
        received_to=received_to,
        correlation_id=correlation_id,
        external_batch_id=external_batch_id,
        offset=offset,
        limit=limit,
    )


@router.get("/ingestion-batches/{batch_id}", response_model=IngestionBatchRead)
def get_batch(
    organization_id: UUID,
    batch_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*INGESTION_READ_ROLES)),
) -> IngestionBatch:
    try:
        return ingestion_batch_service.get(db, organization_id, batch_id)
    except IngestionNotFoundError as exc:
        _translate_error(exc)


@router.post("/ingestion-batches/{batch_id}/transition", response_model=IngestionBatchRead)
def transition_batch(
    organization_id: UUID,
    batch_id: UUID,
    payload: BatchTransition,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*INGESTION_OPERATION_ROLES)),
) -> IngestionBatch:
    try:
        return ingestion_batch_service.transition(db, organization_id, batch_id, payload.status)
    except (IngestionNotFoundError, InvalidIngestionTransitionError) as exc:
        _translate_error(exc)


def _batch_action(
    action: str, db: Session, organization_id: UUID, batch_id: UUID
) -> IngestionBatch:
    try:
        method = cast(
            Callable[[Session, UUID, UUID], IngestionBatch],
            getattr(ingestion_batch_service, action),
        )
        return method(db, organization_id, batch_id)
    except (IngestionNotFoundError, InvalidIngestionTransitionError) as exc:
        _translate_error(exc)


@router.post("/ingestion-batches/{batch_id}/retry", response_model=IngestionBatchRead)
def retry_batch(
    organization_id: UUID,
    batch_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*INGESTION_OPERATION_ROLES)),
) -> IngestionBatch:
    return _batch_action("retry", db, organization_id, batch_id)


@router.post("/ingestion-batches/{batch_id}/quarantine", response_model=IngestionBatchRead)
def quarantine_batch(
    organization_id: UUID,
    batch_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*INGESTION_OPERATION_ROLES)),
) -> IngestionBatch:
    return _batch_action("quarantine", db, organization_id, batch_id)


@router.post("/ingestion-batches/{batch_id}/release", response_model=IngestionBatchRead)
def release_batch(
    organization_id: UUID,
    batch_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*INGESTION_RELEASE_ROLES)),
) -> IngestionBatch:
    return _batch_action("release", db, organization_id, batch_id)


@router.post("/ingestion-batches/{batch_id}/cancel", response_model=IngestionBatchRead)
def cancel_batch(
    organization_id: UUID,
    batch_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*INGESTION_OPERATION_ROLES)),
) -> IngestionBatch:
    return _batch_action("cancel", db, organization_id, batch_id)


@router.patch("/ingestion-batches/{batch_id}/counts", response_model=IngestionBatchRead)
def update_batch_counts(
    organization_id: UUID,
    batch_id: UUID,
    payload: BatchCountsUpdate,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*INGESTION_OPERATION_ROLES)),
) -> IngestionBatch:
    try:
        return ingestion_batch_service.update_counts(db, organization_id, batch_id, payload)
    except (IngestionNotFoundError, InvalidIngestionTransitionError) as exc:
        _translate_error(exc)


@router.post("/ingestion-batches/{batch_id}/failure", response_model=IngestionBatchRead)
def record_batch_failure(
    organization_id: UUID,
    batch_id: UUID,
    payload: BatchFailure,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*INGESTION_OPERATION_ROLES)),
) -> IngestionBatch:
    try:
        return ingestion_batch_service.record_failure(
            db,
            organization_id,
            batch_id,
            payload.failure_code,
            payload.failure_summary,
        )
    except (IngestionNotFoundError, InvalidIngestionTransitionError) as exc:
        _translate_error(exc)


@router.post("/datasets", response_model=DatasetRead, status_code=status.HTTP_201_CREATED)
def create_dataset(
    organization_id: UUID,
    payload: DatasetCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*INGESTION_ADMIN_ROLES)),
) -> Dataset:
    try:
        return dataset_service.create(db, organization_id, payload, access.user.user_id)
    except (IngestionConflictError, IngestionTenantMismatchError) as exc:
        _translate_error(exc)


@router.get("/datasets", response_model=list[DatasetRead])
def list_datasets(
    organization_id: UUID,
    source_system_id: UUID | None = None,
    domain: str | None = None,
    dataset_type: DatasetType | None = None,
    dataset_status: DatasetStatus | None = Query(default=None, alias="status"),
    sensitivity: DataClassification | None = None,
    schema_status: SchemaStatus | None = None,
    search: str | None = Query(default=None, max_length=200),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*INGESTION_READ_ROLES)),
) -> list[Dataset]:
    return dataset_service.list(
        db,
        organization_id,
        source_system_id=source_system_id,
        domain=domain,
        dataset_type=dataset_type,
        status=dataset_status,
        sensitivity=sensitivity,
        schema_status=schema_status,
        search=search,
        offset=offset,
        limit=limit,
    )


@router.get("/datasets/{dataset_id}", response_model=DatasetRead)
def get_dataset(
    organization_id: UUID,
    dataset_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*INGESTION_READ_ROLES)),
) -> Dataset:
    try:
        return dataset_service.get(db, organization_id, dataset_id)
    except IngestionNotFoundError as exc:
        _translate_error(exc)


@router.patch("/datasets/{dataset_id}", response_model=DatasetRead)
def update_dataset(
    organization_id: UUID,
    dataset_id: UUID,
    payload: DatasetUpdate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*INGESTION_ADMIN_ROLES)),
) -> Dataset:
    try:
        return dataset_service.update(db, organization_id, dataset_id, payload, access.user.user_id)
    except (
        IngestionNotFoundError,
        IngestionConflictError,
        InvalidIngestionTransitionError,
    ) as exc:
        _translate_error(exc)


def _dataset_action(
    target: DatasetStatus,
    db: Session,
    organization_id: UUID,
    dataset_id: UUID,
    actor_user_id: UUID,
) -> Dataset:
    try:
        return dataset_service.transition(db, organization_id, dataset_id, target, actor_user_id)
    except (IngestionNotFoundError, InvalidIngestionTransitionError) as exc:
        _translate_error(exc)


@router.post("/datasets/{dataset_id}/activate", response_model=DatasetRead)
def activate_dataset(
    organization_id: UUID,
    dataset_id: UUID,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*INGESTION_ADMIN_ROLES)),
) -> Dataset:
    return _dataset_action(
        DatasetStatus.ACTIVE,
        db,
        organization_id,
        dataset_id,
        access.user.user_id,
    )


@router.post("/datasets/{dataset_id}/pause", response_model=DatasetRead)
def pause_dataset(
    organization_id: UUID,
    dataset_id: UUID,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*INGESTION_ADMIN_ROLES)),
) -> Dataset:
    return _dataset_action(
        DatasetStatus.PAUSED,
        db,
        organization_id,
        dataset_id,
        access.user.user_id,
    )


@router.post("/datasets/{dataset_id}/deprecate", response_model=DatasetRead)
def deprecate_dataset(
    organization_id: UUID,
    dataset_id: UUID,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*INGESTION_ADMIN_ROLES)),
) -> Dataset:
    return _dataset_action(
        DatasetStatus.DEPRECATED,
        db,
        organization_id,
        dataset_id,
        access.user.user_id,
    )


@router.post("/datasets/{dataset_id}/decommission", response_model=DatasetRead)
def decommission_dataset(
    organization_id: UUID,
    dataset_id: UUID,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*INGESTION_ADMIN_ROLES)),
) -> Dataset:
    return _dataset_action(
        DatasetStatus.DECOMMISSIONED,
        db,
        organization_id,
        dataset_id,
        access.user.user_id,
    )


@router.post(
    "/datasets/{dataset_id}/versions",
    response_model=DatasetVersionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_dataset_version(
    organization_id: UUID,
    dataset_id: UUID,
    payload: DatasetVersionCreate,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*INGESTION_OPERATION_ROLES)),
) -> DatasetVersion:
    try:
        return dataset_version_service.create(db, organization_id, dataset_id, payload)
    except (
        IngestionNotFoundError,
        IngestionConflictError,
        IngestionTenantMismatchError,
        InvalidIngestionTransitionError,
    ) as exc:
        _translate_error(exc)


@router.get("/datasets/{dataset_id}/versions", response_model=list[DatasetVersionRead])
def list_dataset_versions(
    organization_id: UUID,
    dataset_id: UUID,
    version_status: DatasetVersionStatus | None = Query(default=None, alias="status"),
    ingestion_batch_id: UUID | None = None,
    received_from: datetime | None = None,
    received_to: datetime | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*INGESTION_READ_ROLES)),
) -> list[DatasetVersion]:
    try:
        dataset_service.get(db, organization_id, dataset_id)
        return dataset_version_service.list(
            db,
            organization_id,
            dataset_id=dataset_id,
            ingestion_batch_id=ingestion_batch_id,
            status=version_status,
            received_from=received_from,
            received_to=received_to,
            offset=offset,
            limit=limit,
        )
    except IngestionNotFoundError as exc:
        _translate_error(exc)


@router.get(
    "/datasets/{dataset_id}/versions/{version_id}",
    response_model=DatasetVersionRead,
)
def get_dataset_version(
    organization_id: UUID,
    dataset_id: UUID,
    version_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*INGESTION_READ_ROLES)),
) -> DatasetVersion:
    try:
        return dataset_version_service.get(db, organization_id, dataset_id, version_id)
    except IngestionNotFoundError as exc:
        _translate_error(exc)


@router.post(
    "/datasets/{dataset_id}/versions/{version_id}/transition",
    response_model=DatasetVersionRead,
)
def transition_dataset_version(
    organization_id: UUID,
    dataset_id: UUID,
    version_id: UUID,
    payload: DatasetVersionTransition,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*INGESTION_OPERATION_ROLES)),
) -> DatasetVersion:
    try:
        return dataset_version_service.transition(
            db, organization_id, dataset_id, version_id, payload.status
        )
    except (IngestionNotFoundError, InvalidIngestionTransitionError) as exc:
        _translate_error(exc)


@router.patch(
    "/datasets/{dataset_id}/versions/{version_id}/counts",
    response_model=DatasetVersionRead,
)
def update_dataset_version_counts(
    organization_id: UUID,
    dataset_id: UUID,
    version_id: UUID,
    payload: DatasetVersionCountsUpdate,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*INGESTION_OPERATION_ROLES)),
) -> DatasetVersion:
    try:
        return dataset_version_service.update_counts(
            db, organization_id, dataset_id, version_id, payload
        )
    except (IngestionNotFoundError, InvalidIngestionTransitionError) as exc:
        _translate_error(exc)


@router.get(
    "/ingestion-batches/{batch_id}/dataset-versions",
    response_model=list[DatasetVersionRead],
)
def list_batch_dataset_versions(
    organization_id: UUID,
    batch_id: UUID,
    version_status: DatasetVersionStatus | None = Query(default=None, alias="status"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*INGESTION_READ_ROLES)),
) -> list[DatasetVersion]:
    try:
        ingestion_batch_service.get(db, organization_id, batch_id)
        return dataset_version_service.list(
            db,
            organization_id,
            ingestion_batch_id=batch_id,
            status=version_status,
            offset=offset,
            limit=limit,
        )
    except IngestionNotFoundError as exc:
        _translate_error(exc)
