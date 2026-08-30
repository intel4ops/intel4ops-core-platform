from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.authorization import OrganizationAccess, require_organization_roles
from app.auth.permissions import ANALYSIS_CASE_READ_ROLES
from app.db.session import get_db
from app.schemas.entities import (
    EntityDetailRead,
    EntityGraphEdgeRead,
    EntityGraphNodeRead,
    EntityGraphRead,
    EntityListRead,
    EntityObservationRead,
    EntityRead,
    RelationshipListRead,
    RelationshipRead,
)
from app.services.analysis_case_entities_service import analysis_case_entities_service

router = APIRouter(prefix="/api/v1/organizations/{organization_id}/analysis-cases")


@router.get("/{case_id}/entities", response_model=EntityListRead)
def list_case_entities(
    organization_id: UUID,
    case_id: UUID,
    run_id: UUID | None = None,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ANALYSIS_CASE_READ_ROLES)),
) -> object:
    resolved_run_id, entities = analysis_case_entities_service.list_entities(
        db, organization_id, case_id, run_id
    )
    return EntityListRead(
        analysis_case_id=case_id,
        run_id=resolved_run_id,
        entities=[EntityRead.model_validate(e) for e in entities],
    )


@router.get("/{case_id}/entities/{entity_id}", response_model=EntityDetailRead)
def get_case_entity(
    organization_id: UUID,
    case_id: UUID,
    entity_id: UUID,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ANALYSIS_CASE_READ_ROLES)),
) -> object:
    result = analysis_case_entities_service.get_entity(db, organization_id, case_id, entity_id)
    if result is None:
        raise HTTPException(
            status_code=404, detail={"code": "CANONICAL_ENTITY_NOT_FOUND", "message": "Not found"}
        )
    entity, observations = result
    return EntityDetailRead(
        **EntityRead.model_validate(entity).model_dump(),
        observations=[EntityObservationRead.model_validate(o) for o in observations],
    )


@router.get("/{case_id}/relationships", response_model=RelationshipListRead)
def list_case_relationships(
    organization_id: UUID,
    case_id: UUID,
    run_id: UUID | None = None,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ANALYSIS_CASE_READ_ROLES)),
) -> object:
    resolved_run_id, relationships = analysis_case_entities_service.list_relationships(
        db, organization_id, case_id, run_id
    )
    return RelationshipListRead(
        analysis_case_id=case_id,
        run_id=resolved_run_id,
        relationships=[RelationshipRead.model_validate(r) for r in relationships],
    )


@router.get("/{case_id}/relationships/{relationship_id}", response_model=RelationshipRead)
def get_case_relationship(
    organization_id: UUID,
    case_id: UUID,
    relationship_id: UUID,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ANALYSIS_CASE_READ_ROLES)),
) -> object:
    relationship = analysis_case_entities_service.get_relationship(
        db, organization_id, case_id, relationship_id
    )
    if relationship is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "CANONICAL_RELATIONSHIP_NOT_FOUND", "message": "Not found"},
        )
    return RelationshipRead.model_validate(relationship)


@router.get("/{case_id}/entity-graph", response_model=EntityGraphRead)
def get_case_entity_graph(
    organization_id: UUID,
    case_id: UUID,
    run_id: UUID | None = None,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ANALYSIS_CASE_READ_ROLES)),
) -> object:
    resolved_run_id, entities, relationships = analysis_case_entities_service.get_entity_graph(
        db, organization_id, case_id, run_id
    )
    return EntityGraphRead(
        analysis_case_id=case_id,
        run_id=resolved_run_id,
        nodes=[
            EntityGraphNodeRead(
                id=e.id,
                entity_type=e.entity_type,
                canonical_key=e.canonical_key,
                display_label=e.display_label,
                entity_identity_confidence=e.entity_identity_confidence,
            )
            for e in entities
        ],
        edges=[
            EntityGraphEdgeRead(
                id=r.id,
                left_entity_id=r.left_entity_id,
                right_entity_id=r.right_entity_id,
                relationship_type=r.relationship_type,
                cardinality=r.cardinality,
                status=r.status,
                relationship_confidence=r.relationship_confidence,
            )
            for r in relationships
        ],
    )
