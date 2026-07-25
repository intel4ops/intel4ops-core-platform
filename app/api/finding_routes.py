from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.authorization import OrganizationAccess, require_organization_roles
from app.auth.permissions import (
    FINDING_ADMIN_ROLES,
    FINDING_READ_ROLES,
    FINDING_REVIEW_ROLES,
)
from app.db.session import get_db
from app.models.entities import Finding
from app.models.findings import (
    FindingCalculationTrace,
    FindingReview,
    FindingRuleTrace,
    FindingStatusHistory,
)
from app.schemas.findings import (
    CalculationTraceRead,
    EvidenceBundleRead,
    EvidenceItemRead,
    EvidenceResponse,
    FindingPage,
    FindingRead,
    FindingSeverity,
    FindingStatusValue,
    FindingType,
    LifecycleCommand,
    ReviewCreate,
    ReviewRead,
    RuleTraceRead,
    StatusHistoryRead,
)
from app.services.finding_platform_service import (
    FindingPlatformError,
    finding_evidence_service,
    finding_lifecycle_service,
    finding_query_service,
    finding_review_service,
)

router = APIRouter(prefix="/api/v1/organizations/{organization_id}/findings")


def _error(exc: FindingPlatformError) -> HTTPException:
    status_code = 404 if exc.code == "FINDING_NOT_FOUND" else 409
    return HTTPException(
        status_code=status_code,
        detail={"code": exc.code, "message": str(exc)},
    )


@router.get("", response_model=FindingPage)
def list_findings(
    organization_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    status: FindingStatusValue | None = None,
    finding_type: FindingType | None = None,
    severity: FindingSeverity | None = None,
    domain: str | None = Query(default=None, max_length=100),
    process: str | None = Query(default=None, max_length=100),
    industry_pack: str | None = Query(default=None, max_length=100),
    definition_code: str | None = Query(default=None, max_length=100),
    detected_from: datetime | None = None,
    detected_to: datetime | None = None,
    occurrence_from: datetime | None = None,
    occurrence_to: datetime | None = None,
    minimum_exposure: Decimal | None = None,
    currency: str | None = Query(default=None, min_length=3, max_length=3),
    review_state: str | None = Query(default=None, max_length=30),
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*FINDING_READ_ROLES)),
) -> FindingPage:
    items, total = finding_query_service.list(
        db,
        organization_id,
        page=page,
        page_size=page_size,
        status=status.value if status else None,
        finding_type=finding_type.value if finding_type else None,
        severity=severity.value if severity else None,
        domain=domain,
        process=process,
        industry_pack=industry_pack,
        definition_code=definition_code,
        detected_from=detected_from,
        detected_to=detected_to,
        occurrence_from=occurrence_from,
        occurrence_to=occurrence_to,
        minimum_exposure=minimum_exposure,
        currency=currency.upper() if currency else None,
        review_state=review_state,
    )
    return FindingPage(
        items=[FindingRead.model_validate(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/{finding_id}", response_model=FindingRead)
def get_finding(
    organization_id: UUID,
    finding_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*FINDING_READ_ROLES)),
) -> Finding:
    try:
        return finding_query_service.get(db, organization_id, finding_id)
    except FindingPlatformError as exc:
        raise _error(exc) from exc


@router.get("/{finding_id}/evidence", response_model=EvidenceResponse)
def get_evidence(
    organization_id: UUID,
    finding_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*FINDING_READ_ROLES)),
) -> EvidenceResponse:
    try:
        bundle, items = finding_evidence_service.get(db, organization_id, finding_id)
    except FindingPlatformError as exc:
        raise _error(exc) from exc
    return EvidenceResponse(
        bundle=EvidenceBundleRead.model_validate(bundle),
        items=[EvidenceItemRead.model_validate(item) for item in items],
    )


@router.get(
    "/{finding_id}/calculation-trace",
    response_model=list[CalculationTraceRead],
)
def get_calculation_trace(
    organization_id: UUID,
    finding_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*FINDING_READ_ROLES)),
) -> list[FindingCalculationTrace]:
    try:
        return finding_evidence_service.calculation_traces(db, organization_id, finding_id)
    except FindingPlatformError as exc:
        raise _error(exc) from exc


@router.get("/{finding_id}/rule-trace", response_model=list[RuleTraceRead])
def get_rule_trace(
    organization_id: UUID,
    finding_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*FINDING_READ_ROLES)),
) -> list[FindingRuleTrace]:
    try:
        return finding_evidence_service.rule_traces(db, organization_id, finding_id)
    except FindingPlatformError as exc:
        raise _error(exc) from exc


@router.post("/{finding_id}/reviews", response_model=ReviewRead, status_code=201)
def create_review(
    organization_id: UUID,
    finding_id: UUID,
    payload: ReviewCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*FINDING_REVIEW_ROLES)),
) -> FindingReview:
    reviewer_role = access.membership.role if access.membership else "platform_admin"
    try:
        return finding_review_service.create(
            db,
            organization_id,
            finding_id,
            payload,
            access.user.user_id,
            reviewer_role,
        )
    except FindingPlatformError as exc:
        raise _error(exc) from exc


@router.get("/{finding_id}/reviews", response_model=list[ReviewRead])
def list_reviews(
    organization_id: UUID,
    finding_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*FINDING_READ_ROLES)),
) -> list[FindingReview]:
    try:
        return finding_review_service.list(db, organization_id, finding_id)
    except FindingPlatformError as exc:
        raise _error(exc) from exc


@router.get(
    "/{finding_id}/status-history",
    response_model=list[StatusHistoryRead],
)
def get_status_history(
    organization_id: UUID,
    finding_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*FINDING_READ_ROLES)),
) -> list[FindingStatusHistory]:
    try:
        return finding_lifecycle_service.history(db, organization_id, finding_id)
    except FindingPlatformError as exc:
        raise _error(exc) from exc


def _lifecycle(
    db: Session,
    organization_id: UUID,
    finding_id: UUID,
    status: FindingStatusValue,
    command: LifecycleCommand,
    actor_user_id: UUID,
) -> Finding:
    try:
        return finding_lifecycle_service.transition(
            db,
            organization_id,
            finding_id,
            status,
            command,
            actor_user_id,
        )
    except FindingPlatformError as exc:
        raise _error(exc) from exc


@router.post("/{finding_id}/publish", response_model=FindingRead)
def publish_finding(
    organization_id: UUID,
    finding_id: UUID,
    payload: LifecycleCommand,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*FINDING_ADMIN_ROLES)),
) -> Finding:
    return _lifecycle(
        db,
        organization_id,
        finding_id,
        FindingStatusValue.PUBLISHED,
        payload,
        access.user.user_id,
    )


def _add_lifecycle_route(path: str, target: FindingStatusValue) -> None:
    async def command(
        organization_id: UUID,
        finding_id: UUID,
        payload: LifecycleCommand,
        db: Session = Depends(get_db),
        access: OrganizationAccess = Depends(require_organization_roles(*FINDING_ADMIN_ROLES)),
    ) -> Finding:
        return _lifecycle(
            db,
            organization_id,
            finding_id,
            target,
            payload,
            access.user.user_id,
        )

    router.add_api_route(
        "/{finding_id}/" + path,
        command,
        methods=["POST"],
        response_model=FindingRead,
        name=f"{path}_finding",
    )


for _path, _target in (
    ("confirm", FindingStatusValue.CONFIRMED),
    ("dismiss", FindingStatusValue.DISMISSED),
    ("supersede", FindingStatusValue.SUPERSEDED),
    ("resolve", FindingStatusValue.RESOLVED),
    ("archive", FindingStatusValue.ARCHIVED),
):
    _add_lifecycle_route(_path, _target)
