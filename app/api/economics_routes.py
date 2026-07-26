from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.auth.authorization import OrganizationAccess, require_organization_roles
from app.auth.permissions import (
    ECONOMICS_APPROVE_ROLES,
    ECONOMICS_CALCULATE_ROLES,
    ECONOMICS_PORTFOLIO_ROLES,
    ECONOMICS_READ_ROLES,
    ECONOMICS_WRITE_ROLES,
)
from app.db.session import get_db
from app.schemas.economics import (
    ActionLinkCreate,
    AssumptionCreate,
    AssumptionRead,
    BaselineRead,
    CalculateCreate,
    CalculationRead,
    DecisionCreate,
    DecisionRead,
    EconomicAuditRead,
    FindingLinkCreate,
    OpportunityCreate,
    OpportunityPage,
    OpportunityRead,
    OpportunityUpdate,
    OverlapGroupCreate,
    OverlapMemberCreate,
    PortfolioSummary,
    PrioritizationRead,
    PrioritizeCreate,
    RankingItem,
    ScenarioCreate,
    ScenarioRead,
)
from app.services.economics_service import EconomicsServiceError, economics_service

router = APIRouter(prefix="/api/v1/organizations/{organization_id}")


def _raise(exc: EconomicsServiceError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status, detail={"code": exc.code, "message": str(exc)}
    ) from exc


def _role(access: OrganizationAccess) -> str:
    return access.membership.role if access.membership is not None else "platform_admin"


@router.post("/recovery-opportunities", response_model=OpportunityRead, status_code=201)
def create_opportunity(
    organization_id: UUID,
    payload: OpportunityCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ECONOMICS_WRITE_ROLES)),
) -> object:
    return economics_service.create(db, organization_id, payload, access.user.user_id)


@router.get("/recovery-opportunities", response_model=OpportunityPage)
def list_opportunities(
    organization_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    status: str | None = None,
    priority: str | None = None,
    currency: str | None = Query(default=None, pattern=r"^[A-Z]{3}$"),
    minimum_net_benefit: float | None = None,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*ECONOMICS_READ_ROLES)),
) -> OpportunityPage:
    from decimal import Decimal

    rows, total = economics_service.list_opportunities(
        db,
        organization_id,
        page,
        page_size,
        status=status,
        priority=priority,
        currency=currency,
        minimum_net_benefit=(
            Decimal(str(minimum_net_benefit)) if minimum_net_benefit is not None else None
        ),
    )
    return OpportunityPage(items=rows, page=page, page_size=page_size, total=total)


@router.get("/recovery-opportunities/{opportunity_id}", response_model=OpportunityRead)
def get_opportunity(
    organization_id: UUID,
    opportunity_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*ECONOMICS_READ_ROLES)),
) -> object:
    try:
        return economics_service.get(db, organization_id, opportunity_id)
    except EconomicsServiceError as exc:
        _raise(exc)


@router.patch("/recovery-opportunities/{opportunity_id}", response_model=OpportunityRead)
def update_opportunity(
    organization_id: UUID,
    opportunity_id: UUID,
    payload: OpportunityUpdate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ECONOMICS_WRITE_ROLES)),
) -> object:
    try:
        return economics_service.update(
            db, organization_id, opportunity_id, payload, access.user.user_id
        )
    except EconomicsServiceError as exc:
        _raise(exc)


@router.post("/recovery-opportunities/{opportunity_id}/findings", status_code=201)
def link_finding(
    organization_id: UUID,
    opportunity_id: UUID,
    payload: FindingLinkCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ECONOMICS_WRITE_ROLES)),
) -> object:
    try:
        return jsonable_encoder(
            economics_service.add_finding(
                db, organization_id, opportunity_id, payload, access.user.user_id
            )
        )
    except EconomicsServiceError as exc:
        _raise(exc)


@router.post("/recovery-opportunities/{opportunity_id}/actions", status_code=201)
def link_action(
    organization_id: UUID,
    opportunity_id: UUID,
    payload: ActionLinkCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ECONOMICS_WRITE_ROLES)),
) -> object:
    try:
        return jsonable_encoder(
            economics_service.add_action(
                db, organization_id, opportunity_id, payload, access.user.user_id
            )
        )
    except EconomicsServiceError as exc:
        _raise(exc)


@router.post(
    "/recovery-opportunities/{opportunity_id}/scenarios",
    response_model=ScenarioRead,
    status_code=201,
)
def create_scenario(
    organization_id: UUID,
    opportunity_id: UUID,
    payload: ScenarioCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ECONOMICS_WRITE_ROLES)),
) -> object:
    try:
        return economics_service.create_scenario(
            db, organization_id, opportunity_id, payload, access.user.user_id
        )
    except EconomicsServiceError as exc:
        _raise(exc)


@router.get(
    "/recovery-opportunities/{opportunity_id}/scenarios",
    response_model=list[ScenarioRead],
)
def list_scenarios(
    organization_id: UUID,
    opportunity_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*ECONOMICS_READ_ROLES)),
) -> object:
    try:
        return economics_service.scenarios(db, organization_id, opportunity_id)
    except EconomicsServiceError as exc:
        _raise(exc)


@router.get(
    "/recovery-opportunities/{opportunity_id}/scenarios/{scenario_id}",
    response_model=ScenarioRead,
)
def get_scenario(
    organization_id: UUID,
    opportunity_id: UUID,
    scenario_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*ECONOMICS_READ_ROLES)),
) -> object:
    try:
        return economics_service.get_scenario(db, organization_id, opportunity_id, scenario_id)
    except EconomicsServiceError as exc:
        _raise(exc)


@router.post(
    "/recovery-opportunities/{opportunity_id}/assumptions",
    response_model=AssumptionRead,
    status_code=201,
)
@router.patch(
    "/recovery-opportunities/{opportunity_id}/assumptions/{_assumption_id}",
    response_model=AssumptionRead,
)
def create_assumption_version(
    organization_id: UUID,
    opportunity_id: UUID,
    payload: AssumptionCreate,
    _assumption_id: UUID | None = None,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ECONOMICS_WRITE_ROLES)),
) -> object:
    try:
        return economics_service.add_assumption(
            db, organization_id, opportunity_id, payload, access.user.user_id
        )
    except EconomicsServiceError as exc:
        _raise(exc)


@router.post(
    "/recovery-opportunities/{opportunity_id}/calculate",
    response_model=CalculationRead,
)
@router.post(
    "/recovery-opportunities/{opportunity_id}/recalculate",
    response_model=CalculationRead,
)
def calculate(
    organization_id: UUID,
    opportunity_id: UUID,
    payload: CalculateCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ECONOMICS_CALCULATE_ROLES)),
) -> object:
    try:
        return economics_service.calculate(
            db, organization_id, opportunity_id, payload, access.user.user_id
        )
    except EconomicsServiceError as exc:
        _raise(exc)


@router.post(
    "/recovery-opportunities/{opportunity_id}/prioritize",
    response_model=PrioritizationRead,
)
def prioritize(
    organization_id: UUID,
    opportunity_id: UUID,
    payload: PrioritizeCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ECONOMICS_CALCULATE_ROLES)),
) -> object:
    try:
        return economics_service.prioritize(
            db, organization_id, opportunity_id, payload, access.user.user_id
        )
    except EconomicsServiceError as exc:
        _raise(exc)


def _decide(
    db: Session,
    organization_id: UUID,
    opportunity_id: UUID,
    payload: DecisionCreate,
    access: OrganizationAccess,
) -> object:
    try:
        opportunity, decision, baseline = economics_service.decide(
            db,
            organization_id,
            opportunity_id,
            payload,
            access.user.user_id,
            _role(access),
        )
        return jsonable_encoder(
            {
                "opportunity": OpportunityRead.model_validate(opportunity),
                "decision": DecisionRead.model_validate(decision),
                "baseline": BaselineRead.model_validate(baseline) if baseline else None,
            }
        )
    except EconomicsServiceError as exc:
        _raise(exc)


@router.post("/recovery-opportunities/{opportunity_id}/submit")
@router.post("/recovery-opportunities/{opportunity_id}/defer")
@router.post("/recovery-opportunities/{opportunity_id}/reject")
def decide(
    organization_id: UUID,
    opportunity_id: UUID,
    payload: DecisionCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ECONOMICS_WRITE_ROLES)),
) -> object:
    return _decide(db, organization_id, opportunity_id, payload, access)


@router.post("/recovery-opportunities/{opportunity_id}/approve")
def approve(
    organization_id: UUID,
    opportunity_id: UUID,
    payload: DecisionCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ECONOMICS_APPROVE_ROLES)),
) -> object:
    return _decide(db, organization_id, opportunity_id, payload, access)


@router.get(
    "/recovery-opportunities/{opportunity_id}/economics",
    response_model=CalculationRead,
)
def economics(
    organization_id: UUID,
    opportunity_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*ECONOMICS_READ_ROLES)),
) -> object:
    try:
        return economics_service.latest_economics(db, organization_id, opportunity_id)
    except EconomicsServiceError as exc:
        _raise(exc)


@router.get(
    "/recovery-opportunities/{opportunity_id}/priority-explanation",
    response_model=PrioritizationRead,
)
def priority_explanation(
    organization_id: UUID,
    opportunity_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*ECONOMICS_READ_ROLES)),
) -> object:
    try:
        return economics_service.latest_priority(db, organization_id, opportunity_id)
    except EconomicsServiceError as exc:
        _raise(exc)


@router.get(
    "/recovery-opportunities/{opportunity_id}/audit-trail",
    response_model=list[EconomicAuditRead],
)
def audit_trail(
    organization_id: UUID,
    opportunity_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*ECONOMICS_READ_ROLES)),
) -> object:
    try:
        return economics_service.audit(db, organization_id, opportunity_id)
    except EconomicsServiceError as exc:
        _raise(exc)


@router.post("/recovery-overlap-groups", status_code=201)
def create_overlap_group(
    organization_id: UUID,
    payload: OverlapGroupCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ECONOMICS_WRITE_ROLES)),
) -> object:
    return jsonable_encoder(
        economics_service.create_overlap_group(db, organization_id, payload, access.user.user_id)
    )


@router.post("/recovery-overlap-groups/{group_id}/members", status_code=201)
def add_overlap_member(
    organization_id: UUID,
    group_id: UUID,
    payload: OverlapMemberCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ECONOMICS_WRITE_ROLES)),
) -> object:
    try:
        return jsonable_encoder(
            economics_service.add_overlap_member(
                db, organization_id, group_id, payload, access.user.user_id
            )
        )
    except EconomicsServiceError as exc:
        _raise(exc)


@router.get("/recovery-portfolio", response_model=PortfolioSummary)
@router.get("/recovery-portfolio/summary", response_model=PortfolioSummary)
def portfolio_summary(
    organization_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*ECONOMICS_PORTFOLIO_ROLES)),
) -> PortfolioSummary:
    return economics_service.portfolio(db, organization_id)[0]


@router.get("/recovery-portfolio/ranking", response_model=list[RankingItem])
def portfolio_ranking(
    organization_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*ECONOMICS_PORTFOLIO_ROLES)),
) -> list[RankingItem]:
    return economics_service.portfolio(db, organization_id)[1]
