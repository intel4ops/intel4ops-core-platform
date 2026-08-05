from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.authorization import (
    OrganizationAccess,
    require_organization_roles,
    require_platform_admin,
)
from app.auth.identity import AuthenticatedUser
from app.auth.permissions import CAUSAL_APPROVE_ROLES, CAUSAL_READ_ROLES, CAUSAL_REVIEW_ROLES
from app.db.session import get_db
from app.models.causal_intelligence import CausalChain, CausalEdge, CausalHypothesis, CausalNode
from app.schemas.causal_intelligence import (
    CausalChainRead,
    CausalChainVersionRead,
    CausalEdgeRead,
    CausalEvidenceLinkCreate,
    CausalEvidenceLinkRead,
    CausalHypothesisCreate,
    CausalHypothesisRead,
    CausalInterventionCreate,
    CausalInterventionRead,
    CausalMethodDefinitionCreate,
    CausalMethodDefinitionRead,
    CausalNodeCreate,
    CausalNodeRead,
    CausalOutcomeAssessmentCreate,
    CausalOutcomeAssessmentRead,
    CausalReviewCreate,
    CausalReviewRead,
    GraphTraversalRead,
    RootCauseRankingEntry,
)
from app.services.causal_intelligence_service import (
    CausalIntelligenceServiceError,
    causal_evaluation_service,
    causal_evidence_service,
    causal_hypothesis_service,
    causal_intervention_service,
    causal_node_service,
    causal_ontology_service,
    causal_outcome_assessment_service,
    causal_review_service,
    root_cause_ranking_service,
)

catalog_router = APIRouter(prefix="/api/v1/causal", tags=["causal-intelligence-governance"])
tenant_router = APIRouter(
    prefix="/api/v1/organizations/{organization_id}/causal", tags=["causal-intelligence"]
)


def _raise(exc: CausalIntelligenceServiceError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status, detail={"code": exc.code, "message": str(exc)}
    ) from exc


def _not_found(code: str, message: str) -> NoReturn:
    raise HTTPException(status_code=404, detail={"code": code, "message": message})


@catalog_router.get("/methods", response_model=list[CausalMethodDefinitionRead])
def list_methods(
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_platform_admin),
) -> object:
    return causal_ontology_service.list_methods(db, None)


@catalog_router.post("/methods", response_model=CausalMethodDefinitionRead, status_code=201)
def create_method(
    payload: CausalMethodDefinitionCreate,
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_platform_admin),
) -> object:
    try:
        return causal_ontology_service.create_method(db, payload)
    except CausalIntelligenceServiceError as exc:
        _raise(exc)


@tenant_router.get("/methods", response_model=list[CausalMethodDefinitionRead])
def tenant_list_methods(
    organization_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*CAUSAL_READ_ROLES)),
) -> object:
    return causal_ontology_service.list_methods(db, organization_id)


@tenant_router.post("/nodes", response_model=CausalNodeRead, status_code=201)
def create_node(
    organization_id: UUID,
    payload: CausalNodeCreate,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*CAUSAL_REVIEW_ROLES)),
) -> object:
    try:
        return causal_node_service.get_or_create(db, organization_id, payload)
    except CausalIntelligenceServiceError as exc:
        _raise(exc)


@tenant_router.get("/nodes/{node_id}", response_model=CausalNodeRead)
def get_node(
    organization_id: UUID,
    node_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*CAUSAL_READ_ROLES)),
) -> object:
    node = db.get(CausalNode, node_id)
    if node is None or node.organization_id != organization_id:
        _not_found("node_not_found", "causal node not found")
    return node


@tenant_router.post("/hypotheses", response_model=CausalHypothesisRead, status_code=201)
def create_hypothesis(
    organization_id: UUID,
    payload: CausalHypothesisCreate,
    db: Session = Depends(get_db),
    actor: OrganizationAccess = Depends(require_organization_roles(*CAUSAL_REVIEW_ROLES)),
) -> object:
    try:
        return causal_hypothesis_service.create(db, organization_id, payload, actor.user.user_id)
    except CausalIntelligenceServiceError as exc:
        _raise(exc)


@tenant_router.post("/hypotheses/{hypothesis_id}/propose", response_model=CausalHypothesisRead)
def propose_hypothesis(
    organization_id: UUID,
    hypothesis_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*CAUSAL_REVIEW_ROLES)),
) -> object:
    try:
        return causal_hypothesis_service.propose(db, organization_id, hypothesis_id)
    except CausalIntelligenceServiceError as exc:
        _raise(exc)


@tenant_router.get("/hypotheses/{hypothesis_id}", response_model=CausalHypothesisRead)
def get_hypothesis(
    organization_id: UUID,
    hypothesis_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*CAUSAL_READ_ROLES)),
) -> object:
    hypothesis = db.get(CausalHypothesis, hypothesis_id)
    if hypothesis is None or hypothesis.organization_id != organization_id:
        _not_found("hypothesis_not_found", "causal hypothesis not found")
    return hypothesis


@tenant_router.post(
    "/hypotheses/{hypothesis_id}/evidence", response_model=CausalEvidenceLinkRead, status_code=201
)
def attach_evidence(
    organization_id: UUID,
    hypothesis_id: UUID,
    payload: CausalEvidenceLinkCreate,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*CAUSAL_REVIEW_ROLES)),
) -> object:
    try:
        return causal_evidence_service.attach(db, organization_id, hypothesis_id, payload)
    except CausalIntelligenceServiceError as exc:
        _raise(exc)


@tenant_router.post("/hypotheses/{hypothesis_id}/evaluate", response_model=CausalHypothesisRead)
def evaluate_hypothesis(
    organization_id: UUID,
    hypothesis_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*CAUSAL_REVIEW_ROLES)),
) -> object:
    try:
        return causal_evaluation_service.evaluate(db, organization_id, hypothesis_id)
    except CausalIntelligenceServiceError as exc:
        _raise(exc)


@tenant_router.post(
    "/hypotheses/{hypothesis_id}/reviews", response_model=CausalReviewRead, status_code=201
)
def review_hypothesis(
    organization_id: UUID,
    hypothesis_id: UUID,
    payload: CausalReviewCreate,
    db: Session = Depends(get_db),
    actor: OrganizationAccess = Depends(require_organization_roles(*CAUSAL_APPROVE_ROLES)),
) -> object:
    try:
        return causal_review_service.review(
            db, organization_id, hypothesis_id, payload, actor.user.user_id
        )
    except CausalIntelligenceServiceError as exc:
        _raise(exc)


@tenant_router.get("/edges/{edge_id}", response_model=CausalEdgeRead)
def get_edge(
    organization_id: UUID,
    edge_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*CAUSAL_READ_ROLES)),
) -> object:
    edge = db.get(CausalEdge, edge_id)
    if edge is None or edge.organization_id != organization_id:
        _not_found("edge_not_found", "causal edge not found")
    return edge


@tenant_router.get("/chains/{chain_id}", response_model=CausalChainRead)
def get_chain(
    organization_id: UUID,
    chain_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*CAUSAL_READ_ROLES)),
) -> object:
    chain = db.get(CausalChain, chain_id)
    if chain is None or chain.organization_id != organization_id:
        _not_found("chain_not_found", "causal chain not found")
    return chain


@tenant_router.post(
    "/chains/{chain_id}/versions", response_model=CausalChainVersionRead, status_code=201
)
def compute_chain_version(
    organization_id: UUID,
    chain_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*CAUSAL_REVIEW_ROLES)),
) -> object:
    chain = db.get(CausalChain, chain_id)
    if chain is None or chain.organization_id != organization_id:
        _not_found("chain_not_found", "causal chain not found")
    try:
        return root_cause_ranking_service.compute_chain_version(db, organization_id, chain)
    except CausalIntelligenceServiceError as exc:
        _raise(exc)


@tenant_router.get("/chains/{chain_id}/graph", response_model=GraphTraversalRead)
def chain_graph(
    organization_id: UUID,
    chain_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*CAUSAL_READ_ROLES)),
) -> object:
    chain = db.get(CausalChain, chain_id)
    if chain is None or chain.organization_id != organization_id:
        _not_found("chain_not_found", "causal chain not found")
    try:
        paths = root_cause_ranking_service.find_paths(
            db, organization_id, chain.root_cause_node_id, chain.terminal_impact_node_id
        )
    except CausalIntelligenceServiceError as exc:
        _raise(exc)
    edges: list[CausalEdge] = [edge for path in paths for edge in path]
    node_ids = {edge.source_node_id for edge in edges} | {edge.target_node_id for edge in edges}
    nodes = [db.get(CausalNode, node_id) for node_id in node_ids]
    return {"nodes": [n for n in nodes if n is not None], "edges": edges}


@tenant_router.get("/root-causes", response_model=list[RootCauseRankingEntry])
def rank_root_causes(
    organization_id: UUID,
    limit: int = 20,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*CAUSAL_READ_ROLES)),
) -> object:
    return root_cause_ranking_service.rank_root_causes(db, organization_id, limit)


@tenant_router.post("/interventions", response_model=CausalInterventionRead, status_code=201)
def create_intervention(
    organization_id: UUID,
    payload: CausalInterventionCreate,
    db: Session = Depends(get_db),
    actor: OrganizationAccess = Depends(require_organization_roles(*CAUSAL_REVIEW_ROLES)),
) -> object:
    try:
        return causal_intervention_service.create(db, organization_id, payload, actor.user.user_id)
    except CausalIntelligenceServiceError as exc:
        _raise(exc)


@tenant_router.post(
    "/outcome-assessments", response_model=CausalOutcomeAssessmentRead, status_code=201
)
def create_outcome_assessment(
    organization_id: UUID,
    payload: CausalOutcomeAssessmentCreate,
    db: Session = Depends(get_db),
    actor: OrganizationAccess = Depends(require_organization_roles(*CAUSAL_APPROVE_ROLES)),
) -> object:
    try:
        return causal_outcome_assessment_service.create(
            db, organization_id, payload, actor.user.user_id
        )
    except CausalIntelligenceServiceError as exc:
        _raise(exc)
