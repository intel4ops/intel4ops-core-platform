from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.authorization import OrganizationAccess, require_organization_roles
from app.auth.commercial import require_commercial_entitlement
from app.auth.permissions import (
    RAW_LINEAGE_ANALYSIS_ROLES,
    RAW_LINEAGE_GOVERNANCE_ROLES,
    RAW_LINEAGE_OPERATION_ROLES,
    RAW_LINEAGE_READ_ROLES,
)
from app.db.session import get_db
from app.models.raw_lineage import (
    ExecutorType,
    IntegrityStatus,
    LineageEventType,
    LineageNodeType,
    LineageRelationshipType,
    ProcessingRunStatus,
    ProcessingRunType,
    RawObjectStatus,
    RawObjectType,
    RawRecordStatus,
    RetentionClass,
)
from app.schemas.raw_lineage import (
    IntegrityVerification,
    LegalHoldRequest,
    LineageEdgeCreate,
    LineageEdgeRead,
    LineageEventRead,
    LineageGraphRead,
    LineageNodeCreate,
    LineageNodeRead,
    ProcessingRunCreate,
    ProcessingRunFailure,
    ProcessingRunRead,
    ProcessingRunResult,
    QuarantineRequest,
    RawRecordBatchCreate,
    RawRecordReferenceCreate,
    RawRecordReferenceRead,
    RawStorageObjectCreate,
    RawStorageObjectRead,
    StatusTransition,
    SupersedeRequest,
)
from app.services.raw_lineage_service import (
    LineageEventService,
    LineageService,
    ProcessingRunService,
    RawLineageConflictError,
    RawLineageNotFoundError,
    RawLineageTenantMismatchError,
    RawRecordReferenceService,
    RawStorageObjectService,
)

router = APIRouter(
    prefix="/api/v1/organizations/{organization_id}",
    dependencies=[
        Depends(require_commercial_entitlement("connect.lineage", *RAW_LINEAGE_READ_ROLES))
    ],
)
events = LineageEventService()
lineage = LineageService(events)
raw_objects = RawStorageObjectService(lineage, events)
raw_records = RawRecordReferenceService(raw_objects, lineage, events)
processing_runs = ProcessingRunService(events)


def _translate(exc: Exception) -> NoReturn:
    if isinstance(exc, (RawLineageConflictError, RawLineageTenantMismatchError)):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/raw-storage-objects",
    response_model=RawStorageObjectRead,
    status_code=status.HTTP_201_CREATED,
)
def register_raw_object(
    organization_id: UUID,
    payload: RawStorageObjectCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*RAW_LINEAGE_OPERATION_ROLES)),
) -> object:
    try:
        return raw_objects.register(db, organization_id, payload, access.user.user_id)
    except (RawLineageConflictError, RawLineageTenantMismatchError) as exc:
        _translate(exc)


@router.get("/raw-storage-objects", response_model=list[RawStorageObjectRead])
def list_raw_objects(
    organization_id: UUID,
    source_system_id: UUID | None = None,
    ingestion_batch_id: UUID | None = None,
    dataset_version_id: UUID | None = None,
    object_type: RawObjectType | None = None,
    object_status: RawObjectStatus | None = Query(default=None, alias="status"),
    integrity_status: IntegrityStatus | None = None,
    retention_class: RetentionClass | None = None,
    legal_hold: bool | None = None,
    checksum: str | None = None,
    received_from: datetime | None = None,
    received_to: datetime | None = None,
    filename_search: str | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*RAW_LINEAGE_READ_ROLES)),
) -> Sequence[object]:
    return raw_objects.list(
        db,
        organization_id,
        source_system_id=source_system_id,
        ingestion_batch_id=ingestion_batch_id,
        dataset_version_id=dataset_version_id,
        object_type=object_type,
        status=object_status,
        integrity_status=integrity_status,
        retention_class=retention_class,
        legal_hold=legal_hold,
        checksum=checksum,
        received_from=received_from,
        received_to=received_to,
        filename_search=filename_search,
        offset=offset,
        limit=limit,
    )


@router.get("/raw-storage-objects/{raw_object_id}", response_model=RawStorageObjectRead)
def get_raw_object(
    organization_id: UUID,
    raw_object_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*RAW_LINEAGE_READ_ROLES)),
) -> object:
    try:
        return raw_objects.get(db, organization_id, raw_object_id)
    except RawLineageNotFoundError as exc:
        _translate(exc)


def _raw_transition(
    db: Session,
    organization_id: UUID,
    raw_object_id: UUID,
    target: RawObjectStatus,
    actor: UUID,
    summary: str | None = None,
) -> object:
    try:
        return raw_objects.transition(
            db, organization_id, raw_object_id, target, actor, summary=summary
        )
    except (RawLineageConflictError, RawLineageNotFoundError) as exc:
        _translate(exc)


@router.post(
    "/raw-storage-objects/{raw_object_id}/transition",
    response_model=RawStorageObjectRead,
)
def transition_raw_object(
    organization_id: UUID,
    raw_object_id: UUID,
    payload: StatusTransition,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*RAW_LINEAGE_OPERATION_ROLES)),
) -> object:
    return _raw_transition(
        db, organization_id, raw_object_id, payload.status, access.user.user_id, payload.summary
    )


@router.post(
    "/raw-storage-objects/{raw_object_id}/verify-integrity",
    response_model=RawStorageObjectRead,
)
def verify_integrity(
    organization_id: UUID,
    raw_object_id: UUID,
    payload: IntegrityVerification,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*RAW_LINEAGE_OPERATION_ROLES)),
) -> object:
    try:
        return raw_objects.verify(db, organization_id, raw_object_id, payload, access.user.user_id)
    except (RawLineageConflictError, RawLineageNotFoundError) as exc:
        _translate(exc)


@router.post("/raw-storage-objects/{raw_object_id}/seal", response_model=RawStorageObjectRead)
def seal_raw_object(
    organization_id: UUID,
    raw_object_id: UUID,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*RAW_LINEAGE_OPERATION_ROLES)),
) -> object:
    return _raw_transition(
        db, organization_id, raw_object_id, RawObjectStatus.SEALED, access.user.user_id
    )


@router.post(
    "/raw-storage-objects/{raw_object_id}/quarantine",
    response_model=RawStorageObjectRead,
)
def quarantine_raw_object(
    organization_id: UUID,
    raw_object_id: UUID,
    payload: QuarantineRequest,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*RAW_LINEAGE_OPERATION_ROLES)),
) -> object:
    return _raw_transition(
        db,
        organization_id,
        raw_object_id,
        RawObjectStatus.QUARANTINED,
        access.user.user_id,
        payload.reason,
    )


@router.post(
    "/raw-storage-objects/{raw_object_id}/supersede",
    response_model=RawStorageObjectRead,
)
def supersede_raw_object(
    organization_id: UUID,
    raw_object_id: UUID,
    payload: SupersedeRequest,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*RAW_LINEAGE_GOVERNANCE_ROLES)),
) -> object:
    try:
        replacement = raw_objects.get(db, organization_id, payload.superseding_raw_object_id)
        if replacement.id == raw_object_id:
            raise RawLineageConflictError("An object cannot supersede itself")
        result = raw_objects.transition(
            db,
            organization_id,
            raw_object_id,
            RawObjectStatus.SUPERSEDED,
            access.user.user_id,
        )
        replacement.supersedes_raw_object_id = raw_object_id
        db.commit()
        return result
    except (RawLineageConflictError, RawLineageNotFoundError) as exc:
        _translate(exc)


@router.post("/raw-storage-objects/{raw_object_id}/archive", response_model=RawStorageObjectRead)
def archive_raw_object(
    organization_id: UUID,
    raw_object_id: UUID,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*RAW_LINEAGE_OPERATION_ROLES)),
) -> object:
    return _raw_transition(
        db, organization_id, raw_object_id, RawObjectStatus.ARCHIVED, access.user.user_id
    )


@router.post(
    "/raw-storage-objects/{raw_object_id}/legal-hold",
    response_model=RawStorageObjectRead,
)
def apply_legal_hold(
    organization_id: UUID,
    raw_object_id: UUID,
    payload: LegalHoldRequest,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*RAW_LINEAGE_GOVERNANCE_ROLES)),
) -> object:
    try:
        return raw_objects.apply_legal_hold(
            db, organization_id, raw_object_id, payload.reason, access.user.user_id
        )
    except RawLineageNotFoundError as exc:
        _translate(exc)


@router.post(
    "/raw-storage-objects/{raw_object_id}/release-legal-hold",
    response_model=RawStorageObjectRead,
)
def release_legal_hold(
    organization_id: UUID,
    raw_object_id: UUID,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*RAW_LINEAGE_GOVERNANCE_ROLES)),
) -> object:
    try:
        return raw_objects.release_legal_hold(
            db, organization_id, raw_object_id, access.user.user_id
        )
    except RawLineageNotFoundError as exc:
        _translate(exc)


@router.post(
    "/raw-storage-objects/{raw_object_id}/request-deletion",
    response_model=RawStorageObjectRead,
)
def request_deletion(
    organization_id: UUID,
    raw_object_id: UUID,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*RAW_LINEAGE_GOVERNANCE_ROLES)),
) -> object:
    return _raw_transition(
        db,
        organization_id,
        raw_object_id,
        RawObjectStatus.DELETION_REQUESTED,
        access.user.user_id,
    )


@router.post(
    "/raw-storage-objects/{raw_object_id}/mark-reference-deleted",
    response_model=RawStorageObjectRead,
)
def mark_reference_deleted(
    organization_id: UUID,
    raw_object_id: UUID,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*RAW_LINEAGE_GOVERNANCE_ROLES)),
) -> object:
    return _raw_transition(
        db,
        organization_id,
        raw_object_id,
        RawObjectStatus.DELETED_REFERENCE,
        access.user.user_id,
    )


@router.post(
    "/raw-storage-objects/{raw_object_id}/record-references",
    response_model=RawRecordReferenceRead,
    status_code=status.HTTP_201_CREATED,
)
def register_record_reference(
    organization_id: UUID,
    raw_object_id: UUID,
    payload: RawRecordReferenceCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*RAW_LINEAGE_OPERATION_ROLES)),
) -> object:
    try:
        return raw_records.register(
            db, organization_id, raw_object_id, payload, access.user.user_id
        )
    except (
        RawLineageConflictError,
        RawLineageNotFoundError,
        RawLineageTenantMismatchError,
    ) as exc:
        _translate(exc)


@router.post(
    "/raw-storage-objects/{raw_object_id}/record-references/batch",
    response_model=list[RawRecordReferenceRead],
)
def register_record_reference_batch(
    organization_id: UUID,
    raw_object_id: UUID,
    payload: RawRecordBatchCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*RAW_LINEAGE_OPERATION_ROLES)),
) -> Sequence[object]:
    try:
        return raw_records.register_batch(
            db, organization_id, raw_object_id, payload.references, access.user.user_id
        )
    except (
        RawLineageConflictError,
        RawLineageNotFoundError,
        RawLineageTenantMismatchError,
    ) as exc:
        _translate(exc)


@router.get(
    "/raw-storage-objects/{raw_object_id}/record-references",
    response_model=list[RawRecordReferenceRead],
)
def list_record_references(
    organization_id: UUID,
    raw_object_id: UUID,
    record_status: RawRecordStatus | None = Query(default=None, alias="status"),
    record_key: str | None = None,
    source_row_number: int | None = Query(default=None, gt=0),
    source_event_id: str | None = None,
    source_timestamp_from: datetime | None = None,
    source_timestamp_to: datetime | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*RAW_LINEAGE_READ_ROLES)),
) -> Sequence[object]:
    return raw_records.list(
        db,
        organization_id,
        raw_object_id=raw_object_id,
        status=record_status,
        record_key=record_key,
        source_row_number=source_row_number,
        source_event_id=source_event_id,
        source_timestamp_from=source_timestamp_from,
        source_timestamp_to=source_timestamp_to,
        offset=offset,
        limit=limit,
    )


@router.get("/raw-record-references/{reference_id}", response_model=RawRecordReferenceRead)
def get_record_reference(
    organization_id: UUID,
    reference_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*RAW_LINEAGE_READ_ROLES)),
) -> object:
    try:
        return raw_records.get(db, organization_id, reference_id)
    except RawLineageNotFoundError as exc:
        _translate(exc)


def _set_record_status(
    db: Session,
    organization_id: UUID,
    reference_id: UUID,
    target: RawRecordStatus,
) -> object:
    try:
        return raw_records.set_status(db, organization_id, reference_id, target)
    except (RawLineageConflictError, RawLineageNotFoundError) as exc:
        _translate(exc)


@router.post(
    "/raw-record-references/{reference_id}/exclude",
    response_model=RawRecordReferenceRead,
)
def exclude_record(
    organization_id: UUID,
    reference_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*RAW_LINEAGE_OPERATION_ROLES)),
) -> object:
    return _set_record_status(db, organization_id, reference_id, RawRecordStatus.EXCLUDED)


@router.post(
    "/raw-record-references/{reference_id}/quarantine",
    response_model=RawRecordReferenceRead,
)
def quarantine_record(
    organization_id: UUID,
    reference_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*RAW_LINEAGE_OPERATION_ROLES)),
) -> object:
    return _set_record_status(db, organization_id, reference_id, RawRecordStatus.QUARANTINED)


@router.post(
    "/raw-record-references/{reference_id}/supersede",
    response_model=RawRecordReferenceRead,
)
def supersede_record(
    organization_id: UUID,
    reference_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*RAW_LINEAGE_GOVERNANCE_ROLES)),
) -> object:
    return _set_record_status(db, organization_id, reference_id, RawRecordStatus.SUPERSEDED)


@router.post(
    "/processing-runs",
    response_model=ProcessingRunRead,
    status_code=status.HTTP_201_CREATED,
)
def create_processing_run(
    organization_id: UUID,
    payload: ProcessingRunCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*RAW_LINEAGE_ANALYSIS_ROLES)),
) -> object:
    try:
        return processing_runs.create(db, organization_id, payload, access.user.user_id)
    except RawLineageTenantMismatchError as exc:
        _translate(exc)


@router.get("/processing-runs", response_model=list[ProcessingRunRead])
def list_processing_runs(
    organization_id: UUID,
    run_status: ProcessingRunStatus | None = Query(default=None, alias="status"),
    ingestion_batch_id: UUID | None = None,
    dataset_version_id: UUID | None = None,
    run_type: ProcessingRunType | None = None,
    executor_type: ExecutorType | None = None,
    correlation_id: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*RAW_LINEAGE_READ_ROLES)),
) -> Sequence[object]:
    return processing_runs.list(
        db,
        organization_id,
        status=run_status,
        ingestion_batch_id=ingestion_batch_id,
        dataset_version_id=dataset_version_id,
        run_type=run_type,
        executor_type=executor_type,
        correlation_id=correlation_id,
        created_from=created_from,
        created_to=created_to,
        offset=offset,
        limit=limit,
    )


@router.get("/processing-runs/{run_id}", response_model=ProcessingRunRead)
def get_processing_run(
    organization_id: UUID,
    run_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*RAW_LINEAGE_READ_ROLES)),
) -> object:
    try:
        return processing_runs.get(db, organization_id, run_id)
    except RawLineageNotFoundError as exc:
        _translate(exc)


def _run_transition(
    db: Session,
    organization_id: UUID,
    run_id: UUID,
    target: ProcessingRunStatus,
    actor: UUID,
    result: ProcessingRunResult | None = None,
) -> object:
    try:
        return processing_runs.transition(db, organization_id, run_id, target, actor, result)
    except (RawLineageConflictError, RawLineageNotFoundError) as exc:
        _translate(exc)


@router.post("/processing-runs/{run_id}/start", response_model=ProcessingRunRead)
def start_run(
    organization_id: UUID,
    run_id: UUID,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*RAW_LINEAGE_ANALYSIS_ROLES)),
) -> object:
    return _run_transition(
        db, organization_id, run_id, ProcessingRunStatus.RUNNING, access.user.user_id
    )


@router.post("/processing-runs/{run_id}/complete", response_model=ProcessingRunRead)
def complete_run(
    organization_id: UUID,
    run_id: UUID,
    payload: ProcessingRunResult,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*RAW_LINEAGE_ANALYSIS_ROLES)),
) -> object:
    return _run_transition(
        db,
        organization_id,
        run_id,
        ProcessingRunStatus.COMPLETED,
        access.user.user_id,
        payload,
    )


@router.post("/processing-runs/{run_id}/partial-complete", response_model=ProcessingRunRead)
def partial_complete_run(
    organization_id: UUID,
    run_id: UUID,
    payload: ProcessingRunResult,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*RAW_LINEAGE_ANALYSIS_ROLES)),
) -> object:
    return _run_transition(
        db,
        organization_id,
        run_id,
        ProcessingRunStatus.PARTIALLY_COMPLETED,
        access.user.user_id,
        payload,
    )


@router.post("/processing-runs/{run_id}/fail", response_model=ProcessingRunRead)
def fail_run(
    organization_id: UUID,
    run_id: UUID,
    payload: ProcessingRunFailure,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*RAW_LINEAGE_ANALYSIS_ROLES)),
) -> object:
    try:
        return processing_runs.fail(db, organization_id, run_id, payload, access.user.user_id)
    except (RawLineageConflictError, RawLineageNotFoundError) as exc:
        _translate(exc)


def _simple_run_action(target: ProcessingRunStatus):  # type: ignore[no-untyped-def]
    def endpoint(
        organization_id: UUID,
        run_id: UUID,
        db: Session = Depends(get_db),
        access: OrganizationAccess = Depends(
            require_organization_roles(*RAW_LINEAGE_ANALYSIS_ROLES)
        ),
    ) -> object:
        return _run_transition(db, organization_id, run_id, target, access.user.user_id)

    return endpoint


router.post("/processing-runs/{run_id}/cancel", response_model=ProcessingRunRead)(
    _simple_run_action(ProcessingRunStatus.CANCELLED)
)
router.post("/processing-runs/{run_id}/quarantine", response_model=ProcessingRunRead)(
    _simple_run_action(ProcessingRunStatus.QUARANTINED)
)
router.post("/processing-runs/{run_id}/retry", response_model=ProcessingRunRead)(
    _simple_run_action(ProcessingRunStatus.QUEUED)
)


@router.post("/lineage/nodes", response_model=LineageNodeRead, status_code=status.HTTP_201_CREATED)
def register_lineage_node(
    organization_id: UUID,
    payload: LineageNodeCreate,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*RAW_LINEAGE_ANALYSIS_ROLES)),
) -> object:
    try:
        node = lineage.register_node(db, organization_id, payload)
        db.commit()
        db.refresh(node)
        return node
    except (RawLineageConflictError, RawLineageTenantMismatchError) as exc:
        _translate(exc)


@router.post("/lineage/edges", response_model=LineageEdgeRead, status_code=status.HTTP_201_CREATED)
def register_lineage_edge(
    organization_id: UUID,
    payload: LineageEdgeCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*RAW_LINEAGE_ANALYSIS_ROLES)),
) -> object:
    try:
        return lineage.create_edge(db, organization_id, payload, access.user.user_id)
    except (
        RawLineageConflictError,
        RawLineageNotFoundError,
        RawLineageTenantMismatchError,
    ) as exc:
        _translate(exc)


@router.get("/lineage/nodes/{node_id}", response_model=LineageNodeRead)
def get_lineage_node(
    organization_id: UUID,
    node_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*RAW_LINEAGE_READ_ROLES)),
) -> object:
    try:
        return lineage.get_node(db, organization_id, node_id)
    except RawLineageNotFoundError as exc:
        _translate(exc)


def _graph(
    db: Session,
    organization_id: UUID,
    node_id: UUID,
    direction: str,
    depth: int,
    max_nodes: int,
    relationship_type: LineageRelationshipType | None,
    node_type: LineageNodeType | None,
) -> LineageGraphRead:
    try:
        return lineage.graph(
            db,
            organization_id,
            node_id,
            direction=direction,
            max_depth=depth,
            max_nodes=max_nodes,
            relationship_type=relationship_type,
            node_type=node_type,
        )
    except (RawLineageConflictError, RawLineageNotFoundError) as exc:
        _translate(exc)


@router.get("/lineage/nodes/{node_id}/upstream", response_model=LineageGraphRead)
def upstream_lineage(
    organization_id: UUID,
    node_id: UUID,
    depth: int = Query(default=3, ge=1, le=10),
    max_nodes: int = Query(default=100, ge=1, le=500),
    relationship_type: LineageRelationshipType | None = None,
    node_type: LineageNodeType | None = None,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*RAW_LINEAGE_READ_ROLES)),
) -> LineageGraphRead:
    return _graph(
        db,
        organization_id,
        node_id,
        "upstream",
        depth,
        max_nodes,
        relationship_type,
        node_type,
    )


@router.get("/lineage/nodes/{node_id}/downstream", response_model=LineageGraphRead)
def downstream_lineage(
    organization_id: UUID,
    node_id: UUID,
    depth: int = Query(default=3, ge=1, le=10),
    max_nodes: int = Query(default=100, ge=1, le=500),
    relationship_type: LineageRelationshipType | None = None,
    node_type: LineageNodeType | None = None,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*RAW_LINEAGE_READ_ROLES)),
) -> LineageGraphRead:
    return _graph(
        db,
        organization_id,
        node_id,
        "downstream",
        depth,
        max_nodes,
        relationship_type,
        node_type,
    )


@router.get("/lineage/nodes/{node_id}/graph", response_model=LineageGraphRead)
def lineage_graph(
    organization_id: UUID,
    node_id: UUID,
    depth: int = Query(default=3, ge=1, le=10),
    max_nodes: int = Query(default=100, ge=1, le=500),
    relationship_type: LineageRelationshipType | None = None,
    node_type: LineageNodeType | None = None,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*RAW_LINEAGE_READ_ROLES)),
) -> LineageGraphRead:
    return _graph(
        db,
        organization_id,
        node_id,
        "both",
        depth,
        max_nodes,
        relationship_type,
        node_type,
    )


@router.get("/lineage/events", response_model=list[LineageEventRead])
def list_lineage_events(
    organization_id: UUID,
    event_type: LineageEventType | None = None,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    processing_run_id: UUID | None = None,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*RAW_LINEAGE_READ_ROLES)),
) -> Sequence[object]:
    return events.list(
        db,
        organization_id,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        processing_run_id=processing_run_id,
        occurred_from=occurred_from,
        occurred_to=occurred_to,
        offset=offset,
        limit=limit,
    )


@router.get("/lineage/entities/{entity_type}/{entity_id}", response_model=LineageNodeRead)
def get_lineage_entity(
    organization_id: UUID,
    entity_type: LineageNodeType,
    entity_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*RAW_LINEAGE_READ_ROLES)),
) -> object:
    try:
        return lineage.node_for_entity(db, organization_id, entity_type, entity_id)
    except RawLineageNotFoundError as exc:
        _translate(exc)
