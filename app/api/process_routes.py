from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.authorization import OrganizationAccess, require_organization_roles
from app.auth.permissions import ANALYSIS_CASE_READ_ROLES
from app.db.session import get_db
from app.schemas.process import (
    ActivityListRead,
    ActivityRead,
    EdgeListRead,
    EdgeRead,
    ProcessDetailRead,
    ProcessGraphEdgeRead,
    ProcessGraphNodeRead,
    ProcessGraphRead,
    ProcessGraphSummaryRead,
    ProcessListRead,
    ProcessRead,
)
from app.services.analysis_case_process_service import analysis_case_process_service

router = APIRouter(prefix="/api/v1/organizations/{organization_id}/analysis-cases")


@router.get("/{case_id}/processes", response_model=ProcessListRead)
def list_case_processes(
    organization_id: UUID,
    case_id: UUID,
    run_id: UUID | None = None,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ANALYSIS_CASE_READ_ROLES)),
) -> object:
    resolved_run_id, processes = analysis_case_process_service.list_processes(
        db, organization_id, case_id, run_id
    )
    return ProcessListRead(
        analysis_case_id=case_id,
        run_id=resolved_run_id,
        processes=[ProcessRead.model_validate(p) for p in processes],
    )


@router.get("/{case_id}/processes/{process_id}", response_model=ProcessDetailRead)
def get_case_process(
    organization_id: UUID,
    case_id: UUID,
    process_id: UUID,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ANALYSIS_CASE_READ_ROLES)),
) -> object:
    result = analysis_case_process_service.get_process(db, organization_id, case_id, process_id)
    if result is None:
        raise HTTPException(
            status_code=404, detail={"code": "CANONICAL_PROCESS_NOT_FOUND", "message": "Not found"}
        )
    process, activities, edges = result
    return ProcessDetailRead(
        **ProcessRead.model_validate(process).model_dump(),
        activities=[ActivityRead.model_validate(a) for a in activities],
        edges=[EdgeRead.model_validate(e) for e in edges],
    )


@router.get("/{case_id}/processes/{process_id}/activities", response_model=ActivityListRead)
def list_case_process_activities(
    organization_id: UUID,
    case_id: UUID,
    process_id: UUID,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ANALYSIS_CASE_READ_ROLES)),
) -> object:
    activities = analysis_case_process_service.list_activities(db, organization_id, process_id)
    return ActivityListRead(
        analysis_case_id=case_id,
        process_id=process_id,
        activities=[ActivityRead.model_validate(a) for a in activities],
    )


@router.get("/{case_id}/activities/{activity_id}", response_model=ActivityRead)
def get_case_activity(
    organization_id: UUID,
    case_id: UUID,
    activity_id: UUID,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ANALYSIS_CASE_READ_ROLES)),
) -> object:
    activity = analysis_case_process_service.get_activity(db, organization_id, case_id, activity_id)
    if activity is None:
        raise HTTPException(
            status_code=404, detail={"code": "CANONICAL_ACTIVITY_NOT_FOUND", "message": "Not found"}
        )
    return ActivityRead.model_validate(activity)


@router.get("/{case_id}/processes/{process_id}/edges", response_model=EdgeListRead)
def list_case_process_edges(
    organization_id: UUID,
    case_id: UUID,
    process_id: UUID,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ANALYSIS_CASE_READ_ROLES)),
) -> object:
    edges = analysis_case_process_service.list_edges(db, organization_id, process_id)
    return EdgeListRead(
        analysis_case_id=case_id,
        process_id=process_id,
        edges=[EdgeRead.model_validate(e) for e in edges],
    )


@router.get("/{case_id}/edges/{edge_id}", response_model=EdgeRead)
def get_case_edge(
    organization_id: UUID,
    case_id: UUID,
    edge_id: UUID,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ANALYSIS_CASE_READ_ROLES)),
) -> object:
    edge = analysis_case_process_service.get_edge(db, organization_id, case_id, edge_id)
    if edge is None:
        raise HTTPException(
            status_code=404, detail={"code": "CANONICAL_EDGE_NOT_FOUND", "message": "Not found"}
        )
    return EdgeRead.model_validate(edge)


@router.get("/{case_id}/process-graph", response_model=ProcessGraphRead)
def get_case_process_graph(
    organization_id: UUID,
    case_id: UUID,
    run_id: UUID | None = None,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ANALYSIS_CASE_READ_ROLES)),
) -> object:
    resolved_run_id, activities, edges = analysis_case_process_service.get_process_graph(
        db, organization_id, case_id, run_id
    )
    return ProcessGraphRead(
        analysis_case_id=case_id,
        run_id=resolved_run_id,
        nodes=[
            ProcessGraphNodeRead(
                id=a.id,
                process_id=a.process_id,
                activity_type=a.activity_type,
                state_value=a.state_value,
                occurred_at=a.occurred_at,
                activity_confidence=a.activity_confidence,
            )
            for a in activities
        ],
        edges=[
            ProcessGraphEdgeRead(
                id=e.id,
                from_activity_id=e.from_activity_id,
                to_activity_id=e.to_activity_id,
                edge_type=e.edge_type,
                status=e.status,
                precedence_confidence=e.precedence_confidence,
            )
            for e in edges
        ],
    )


@router.get("/{case_id}/process-graph/summary", response_model=ProcessGraphSummaryRead)
def get_case_process_graph_summary(
    organization_id: UUID,
    case_id: UUID,
    run_id: UUID | None = None,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ANALYSIS_CASE_READ_ROLES)),
) -> object:
    (
        resolved_run_id,
        process_count,
        activity_count,
        edge_count,
        boundary_status_counts,
        status_counts,
        activity_type_counts,
    ) = analysis_case_process_service.get_process_graph_summary(
        db, organization_id, case_id, run_id
    )
    return ProcessGraphSummaryRead(
        analysis_case_id=case_id,
        run_id=resolved_run_id,
        process_count=process_count,
        activity_count=activity_count,
        edge_count=edge_count,
        boundary_status_counts=boundary_status_counts,
        status_counts=status_counts,
        activity_type_counts=activity_type_counts,
    )
