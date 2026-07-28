from typing import Literal, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.authorization import (
    OrganizationAccess,
    require_organization_roles,
    require_platform_admin,
)
from app.auth.commercial import require_registered_application_client
from app.auth.identity import AuthenticatedUser
from app.auth.permissions import (
    KNOWLEDGE_GRAPH_PROJECTION_ROLES,
    KNOWLEDGE_GRAPH_READ_ROLES,
    KNOWLEDGE_GRAPH_TRAVERSAL_ROLES,
)
from app.db.session import get_db
from app.schemas.knowledge_graph import (
    FindingProjectionCreate,
    GraphEntityTypeRead,
    GraphEntityTypeVersionRead,
    GraphExplanationRead,
    GraphHealthRead,
    GraphNodeRead,
    GraphRelationshipTypeRead,
    GraphRelationshipTypeVersionRead,
    GraphTraversalCreate,
    GraphTraversalRead,
    GraphTypeTransition,
    GraphVersionRead,
    ProjectionRead,
)
from app.services.knowledge_graph_service import (
    KnowledgeGraphServiceError,
    graph_projection_service,
    graph_query_service,
    graph_type_catalog_service,
)

catalog_router = APIRouter(
    prefix="/api/v1/enterprise-intelligence/knowledge-graph",
    tags=["enterprise-knowledge-graph"],
    dependencies=[Depends(require_registered_application_client)],
)
tenant_router = APIRouter(
    prefix="/api/v1/organizations/{organization_id}/knowledge-graph",
    tags=["enterprise-knowledge-graph"],
    dependencies=[Depends(require_registered_application_client)],
)


def _raise(exc: KnowledgeGraphServiceError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status,
        detail={"code": exc.code, "message": str(exc)},
    ) from exc


@catalog_router.get("/entity-types", response_model=list[GraphEntityTypeRead])
def entity_types(
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_platform_admin),
) -> object:
    return graph_type_catalog_service.entity_types(db)


@catalog_router.get("/relationship-types", response_model=list[GraphRelationshipTypeRead])
def relationship_types(
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_platform_admin),
) -> object:
    return graph_type_catalog_service.relationship_types(db)


@catalog_router.get(
    "/entity-types/{entity_type_id}/versions",
    response_model=list[GraphEntityTypeVersionRead],
)
def entity_type_versions(
    entity_type_id: UUID,
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_platform_admin),
) -> object:
    return graph_type_catalog_service.entity_type_versions(db, entity_type_id)


@catalog_router.get(
    "/relationship-types/{relationship_type_id}/versions",
    response_model=list[GraphRelationshipTypeVersionRead],
)
def relationship_type_versions(
    relationship_type_id: UUID,
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_platform_admin),
) -> object:
    return graph_type_catalog_service.relationship_type_versions(db, relationship_type_id)


@catalog_router.post("/types/{asset_id}/transition")
def transition_type(
    asset_id: UUID,
    payload: GraphTypeTransition,
    db: Session = Depends(get_db),
    actor: AuthenticatedUser = Depends(require_platform_admin),
) -> object:
    try:
        return graph_type_catalog_service.transition(db, asset_id, payload, actor.user_id)
    except KnowledgeGraphServiceError as exc:
        _raise(exc)


@tenant_router.get("/versions", response_model=list[GraphVersionRead])
def versions(
    organization_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*KNOWLEDGE_GRAPH_READ_ROLES)),
) -> object:
    try:
        return graph_query_service.versions(db, organization_id)
    except KnowledgeGraphServiceError as exc:
        _raise(exc)


@tenant_router.get("/nodes", response_model=list[GraphNodeRead])
def nodes(
    organization_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*KNOWLEDGE_GRAPH_READ_ROLES)),
) -> object:
    try:
        return graph_query_service.nodes(db, organization_id)
    except KnowledgeGraphServiceError as exc:
        _raise(exc)


@tenant_router.get("/nodes/{node_id}", response_model=GraphNodeRead)
def node(
    organization_id: UUID,
    node_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*KNOWLEDGE_GRAPH_READ_ROLES)),
) -> object:
    try:
        return graph_query_service.node(db, organization_id, node_id)
    except KnowledgeGraphServiceError as exc:
        _raise(exc)


@tenant_router.get("/nodes/{node_id}/neighbors", response_model=GraphTraversalRead)
def neighbors(
    organization_id: UUID,
    node_id: UUID,
    direction: Literal["outbound", "inbound", "both"] = "both",
    relationship_codes: list[str] = Query(default=[]),
    minimum_confidence: float = Query(default=0, ge=0, le=1),
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(
        require_organization_roles(*KNOWLEDGE_GRAPH_TRAVERSAL_ROLES)
    ),
) -> object:
    try:
        node_record = graph_query_service.node(db, organization_id, node_id)
        payload = GraphTraversalCreate(
            idempotency_key=(
                f"neighbors:{node_id}:{direction}:"
                f"{','.join(sorted(relationship_codes))}:{minimum_confidence}"
            ),
            start_node_id=node_id,
            graph_version_id=node_record.graph_version_id,
            operation="neighborhood",
            direction=direction,
            relationship_codes=relationship_codes,
            max_depth=1,
            minimum_confidence=minimum_confidence,
        )
        return graph_query_service.traverse(db, organization_id, payload, access.user.user_id)
    except KnowledgeGraphServiceError as exc:
        _raise(exc)


@tenant_router.post("/projections", response_model=ProjectionRead, status_code=201)
def project(
    organization_id: UUID,
    payload: FindingProjectionCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(
        require_organization_roles(*KNOWLEDGE_GRAPH_PROJECTION_ROLES)
    ),
) -> object:
    try:
        return graph_projection_service.project_finding(
            db, organization_id, payload, access.user.user_id
        )
    except KnowledgeGraphServiceError as exc:
        _raise(exc)


@tenant_router.post("/traversals", response_model=GraphTraversalRead, status_code=201)
def traverse(
    organization_id: UUID,
    payload: GraphTraversalCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(
        require_organization_roles(*KNOWLEDGE_GRAPH_TRAVERSAL_ROLES)
    ),
) -> object:
    try:
        return graph_query_service.traverse(db, organization_id, payload, access.user.user_id)
    except KnowledgeGraphServiceError as exc:
        _raise(exc)


@tenant_router.get("/traversals/{run_id}/explanation", response_model=GraphExplanationRead)
def explanation(
    organization_id: UUID,
    run_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*KNOWLEDGE_GRAPH_READ_ROLES)),
) -> object:
    try:
        return graph_query_service.explanation(db, organization_id, run_id)
    except KnowledgeGraphServiceError as exc:
        _raise(exc)


@tenant_router.get("/traversals/{run_id}", response_model=GraphTraversalRead)
def traversal(
    organization_id: UUID,
    run_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*KNOWLEDGE_GRAPH_READ_ROLES)),
) -> object:
    try:
        return graph_query_service.run(db, organization_id, run_id)
    except KnowledgeGraphServiceError as exc:
        _raise(exc)


@tenant_router.get("/health", response_model=GraphHealthRead)
def health(
    organization_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*KNOWLEDGE_GRAPH_READ_ROLES)),
) -> object:
    try:
        return graph_query_service.health(db, organization_id)
    except KnowledgeGraphServiceError as exc:
        _raise(exc)
