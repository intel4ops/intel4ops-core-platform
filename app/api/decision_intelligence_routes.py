from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.authorization import OrganizationAccess, require_organization_roles
from app.auth.permissions import (
    DECISION_APPROVE_ROLES,
    DECISION_AUTHOR_ROLES,
    DECISION_READ_ROLES,
)
from app.db.session import get_db
from app.models.decision_intelligence import (
    DecisionAlternative,
    DecisionAuditEvent,
    DecisionExecution,
    DecisionRecommendation,
    DecisionSolution,
)
from app.schemas.decision_intelligence import (
    DecisionAlternativeRead,
    DecisionApprovalCreate,
    DecisionApprovalRead,
    DecisionConstraintCreate,
    DecisionExecutionCreate,
    DecisionExecutionRead,
    DecisionHistoryEntry,
    DecisionMethodRead,
    DecisionObjectiveCreate,
    DecisionOutcomeCreate,
    DecisionOutcomeRead,
    DecisionProblemCreate,
    DecisionProblemRead,
    DecisionProblemVersionCreate,
    DecisionProblemVersionRead,
    DecisionRecommendationCreate,
    DecisionRecommendationRead,
    DecisionScenarioCreate,
    DecisionScenarioInputCreate,
    DecisionScenarioRead,
    DecisionSensitivityCreate,
    DecisionSolutionRead,
    DecisionVariableCreate,
)
from app.services.decision_intelligence_service import (
    DecisionIntelligenceServiceError,
    decision_approval_service,
    decision_execution_service,
    decision_method_registry_service,
    decision_outcome_service,
    decision_problem_service,
    decision_scenario_service,
    decision_validation_service,
    recommendation_service,
    sensitivity_analysis_service,
)

catalog_router = APIRouter(prefix="/api/v1/decision-methods", tags=["decision-methods"])
tenant_router = APIRouter(
    prefix="/api/v1/organizations/{organization_id}/decisions",
    tags=["decision-intelligence"],
)


def _raise(exc: DecisionIntelligenceServiceError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status, detail={"code": exc.code, "message": str(exc)}
    ) from exc


def _role(access: OrganizationAccess) -> str:
    return "platform_admin" if access.membership is None else str(access.membership.role)


@catalog_router.get("", response_model=list[DecisionMethodRead])
def list_decision_methods() -> object:
    return decision_method_registry_service.list_methods()


@tenant_router.post("/problems", response_model=DecisionProblemRead, status_code=201)
def create_problem(
    organization_id: UUID,
    payload: DecisionProblemCreate,
    db: Session = Depends(get_db),
    actor: OrganizationAccess = Depends(require_organization_roles(*DECISION_AUTHOR_ROLES)),
) -> object:
    try:
        return decision_problem_service.create(db, organization_id, payload, actor.user.user_id)
    except DecisionIntelligenceServiceError as exc:
        _raise(exc)


@tenant_router.post(
    "/problems/{problem_id}/versions",
    response_model=DecisionProblemVersionRead,
    status_code=201,
)
def create_problem_version(
    organization_id: UUID,
    problem_id: UUID,
    payload: DecisionProblemVersionCreate,
    db: Session = Depends(get_db),
    actor: OrganizationAccess = Depends(require_organization_roles(*DECISION_AUTHOR_ROLES)),
) -> object:
    try:
        return decision_problem_service.add_version(
            db, organization_id, problem_id, payload, actor.user.user_id
        )
    except DecisionIntelligenceServiceError as exc:
        _raise(exc)


@tenant_router.post(
    "/problem-versions/{version_id}/publish",
    response_model=DecisionProblemVersionRead,
)
def publish_problem_version(
    organization_id: UUID,
    version_id: UUID,
    db: Session = Depends(get_db),
    actor: OrganizationAccess = Depends(require_organization_roles(*DECISION_APPROVE_ROLES)),
) -> object:
    try:
        return decision_problem_service.publish_version(
            db, organization_id, version_id, actor.user.user_id
        )
    except DecisionIntelligenceServiceError as exc:
        _raise(exc)


@tenant_router.post("/problem-versions/{version_id}/objectives", status_code=201)
def add_objective(
    organization_id: UUID,
    version_id: UUID,
    payload: DecisionObjectiveCreate,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*DECISION_AUTHOR_ROLES)),
) -> object:
    try:
        return decision_problem_service.add_objective(db, organization_id, version_id, payload)
    except DecisionIntelligenceServiceError as exc:
        _raise(exc)


@tenant_router.post("/problem-versions/{version_id}/constraints", status_code=201)
def add_constraint(
    organization_id: UUID,
    version_id: UUID,
    payload: DecisionConstraintCreate,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*DECISION_AUTHOR_ROLES)),
) -> object:
    try:
        return decision_problem_service.add_constraint(db, organization_id, version_id, payload)
    except DecisionIntelligenceServiceError as exc:
        _raise(exc)


@tenant_router.post("/problem-versions/{version_id}/variables", status_code=201)
def add_variable(
    organization_id: UUID,
    version_id: UUID,
    payload: DecisionVariableCreate,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*DECISION_AUTHOR_ROLES)),
) -> object:
    try:
        return decision_problem_service.add_variable(db, organization_id, version_id, payload)
    except DecisionIntelligenceServiceError as exc:
        _raise(exc)


@tenant_router.post("/scenarios", response_model=DecisionScenarioRead, status_code=201)
def create_scenario(
    organization_id: UUID,
    payload: DecisionScenarioCreate,
    db: Session = Depends(get_db),
    actor: OrganizationAccess = Depends(require_organization_roles(*DECISION_AUTHOR_ROLES)),
) -> object:
    try:
        return decision_scenario_service.create(db, organization_id, payload, actor.user.user_id)
    except DecisionIntelligenceServiceError as exc:
        _raise(exc)


@tenant_router.post("/scenarios/{scenario_id}/inputs", status_code=201)
def add_scenario_input(
    organization_id: UUID,
    scenario_id: UUID,
    payload: DecisionScenarioInputCreate,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*DECISION_AUTHOR_ROLES)),
) -> object:
    try:
        return decision_scenario_service.add_input(db, organization_id, scenario_id, payload)
    except DecisionIntelligenceServiceError as exc:
        _raise(exc)


@tenant_router.post("/scenarios/{scenario_id}/validate", response_model=DecisionScenarioRead)
def validate_scenario(
    organization_id: UUID,
    scenario_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*DECISION_AUTHOR_ROLES)),
) -> object:
    try:
        return decision_validation_service.validate(db, organization_id, scenario_id)
    except DecisionIntelligenceServiceError as exc:
        _raise(exc)


@tenant_router.post(
    "/scenarios/{scenario_id}/execute",
    response_model=DecisionExecutionRead,
    status_code=201,
)
def execute_scenario(
    organization_id: UUID,
    scenario_id: UUID,
    payload: DecisionExecutionCreate,
    db: Session = Depends(get_db),
    actor: OrganizationAccess = Depends(require_organization_roles(*DECISION_AUTHOR_ROLES)),
) -> object:
    try:
        return decision_execution_service.execute(
            db, organization_id, scenario_id, payload, actor.user.user_id
        )
    except DecisionIntelligenceServiceError as exc:
        _raise(exc)


@tenant_router.get("/executions/{execution_id}", response_model=DecisionExecutionRead)
def get_execution(
    organization_id: UUID,
    execution_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*DECISION_READ_ROLES)),
) -> object:
    execution = db.get(DecisionExecution, execution_id)
    if execution is None or execution.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Decision execution not found")
    return execution


@tenant_router.get(
    "/executions/{execution_id}/solutions", response_model=list[DecisionSolutionRead]
)
def list_solutions(
    organization_id: UUID,
    execution_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*DECISION_READ_ROLES)),
) -> object:
    return list(
        db.scalars(
            select(DecisionSolution).where(
                DecisionSolution.organization_id == organization_id,
                DecisionSolution.execution_id == execution_id,
            )
        )
    )


@tenant_router.get(
    "/solutions/{solution_id}/alternatives",
    response_model=list[DecisionAlternativeRead],
)
def compare_alternatives(
    organization_id: UUID,
    solution_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*DECISION_READ_ROLES)),
) -> object:
    return list(
        db.scalars(
            select(DecisionAlternative)
            .where(
                DecisionAlternative.organization_id == organization_id,
                DecisionAlternative.solution_id == solution_id,
            )
            .order_by(DecisionAlternative.rank)
        )
    )


@tenant_router.post("/solutions/{solution_id}/sensitivity", status_code=201)
def run_sensitivity(
    organization_id: UUID,
    solution_id: UUID,
    payload: DecisionSensitivityCreate,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*DECISION_AUTHOR_ROLES)),
) -> object:
    try:
        return sensitivity_analysis_service.record(db, organization_id, solution_id, payload)
    except DecisionIntelligenceServiceError as exc:
        _raise(exc)


@tenant_router.post(
    "/recommendations",
    response_model=DecisionRecommendationRead,
    status_code=201,
)
def create_recommendation(
    organization_id: UUID,
    payload: DecisionRecommendationCreate,
    db: Session = Depends(get_db),
    actor: OrganizationAccess = Depends(require_organization_roles(*DECISION_AUTHOR_ROLES)),
) -> object:
    try:
        return recommendation_service.create(db, organization_id, payload, actor.user.user_id)
    except DecisionIntelligenceServiceError as exc:
        _raise(exc)


@tenant_router.get(
    "/recommendations/{recommendation_id}",
    response_model=DecisionRecommendationRead,
)
def get_recommendation(
    organization_id: UUID,
    recommendation_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*DECISION_READ_ROLES)),
) -> object:
    recommendation = db.get(DecisionRecommendation, recommendation_id)
    if recommendation is None or recommendation.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Decision recommendation not found")
    return recommendation


@tenant_router.post(
    "/recommendations/{recommendation_id}/approvals",
    response_model=DecisionApprovalRead,
    status_code=201,
)
def decide_recommendation(
    organization_id: UUID,
    recommendation_id: UUID,
    payload: DecisionApprovalCreate,
    db: Session = Depends(get_db),
    actor: OrganizationAccess = Depends(require_organization_roles(*DECISION_APPROVE_ROLES)),
) -> object:
    try:
        return decision_approval_service.decide(
            db,
            organization_id,
            recommendation_id,
            payload,
            actor.user.user_id,
            _role(actor),
        )
    except DecisionIntelligenceServiceError as exc:
        _raise(exc)


@tenant_router.post("/recommendations/{recommendation_id}/convert", status_code=201)
def convert_recommendation(
    organization_id: UUID,
    recommendation_id: UUID,
    db: Session = Depends(get_db),
    actor: OrganizationAccess = Depends(require_organization_roles(*DECISION_APPROVE_ROLES)),
) -> object:
    try:
        return decision_approval_service.convert_to_action(
            db, organization_id, recommendation_id, actor.user.user_id
        )
    except DecisionIntelligenceServiceError as exc:
        _raise(exc)


@tenant_router.post(
    "/recommendations/{recommendation_id}/outcomes",
    response_model=DecisionOutcomeRead,
    status_code=201,
)
def record_outcome(
    organization_id: UUID,
    recommendation_id: UUID,
    payload: DecisionOutcomeCreate,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*DECISION_AUTHOR_ROLES)),
) -> object:
    try:
        return decision_outcome_service.record(db, organization_id, recommendation_id, payload)
    except DecisionIntelligenceServiceError as exc:
        _raise(exc)


@tenant_router.get("/history", response_model=list[DecisionHistoryEntry])
def decision_history(
    organization_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*DECISION_READ_ROLES)),
) -> object:
    return list(
        db.scalars(
            select(DecisionAuditEvent)
            .where(DecisionAuditEvent.organization_id == organization_id)
            .order_by(DecisionAuditEvent.occurred_at.desc())
        )
    )
