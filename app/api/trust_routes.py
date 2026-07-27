from __future__ import annotations

from collections.abc import Sequence
from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.authorization import OrganizationAccess, require_organization_roles
from app.auth.commercial import require_commercial_entitlement
from app.auth.permissions import TRUST_EXECUTION_ROLES, TRUST_READ_ROLES
from app.db.session import get_db
from app.schemas.trust import (
    AnalyticalReadinessDecisionRead,
    PaginatedTrustEvidence,
    TrustAssessmentCreate,
    TrustAssessmentRead,
    TrustEvidenceRead,
    TrustRuleResultRead,
)
from app.services.trust_service import (
    NoApplicableTrustRulesError,
    TrustConfigurationError,
    TrustNotFoundError,
    TrustTenantMismatchError,
    trust_assessment_service,
)

router = APIRouter(
    prefix="/api/v1/organizations/{organization_id}",
    dependencies=[
        Depends(require_commercial_entitlement("trust.rule_execution", *TRUST_READ_ROLES))
    ],
)


def _translate(exc: Exception) -> NoReturn:
    if isinstance(exc, TrustConfigurationError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, NoApplicableTrustRulesError):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/datasets/{dataset_id}/trust-assessments",
    response_model=TrustAssessmentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_trust_assessment(
    organization_id: UUID,
    dataset_id: UUID,
    payload: TrustAssessmentCreate,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*TRUST_EXECUTION_ROLES)),
) -> object:
    try:
        return trust_assessment_service.create_and_execute(db, organization_id, dataset_id, payload)
    except (
        NoApplicableTrustRulesError,
        TrustConfigurationError,
        TrustNotFoundError,
        TrustTenantMismatchError,
    ) as exc:
        _translate(exc)


@router.get(
    "/trust-assessments/{assessment_id}",
    response_model=TrustAssessmentRead,
)
def get_trust_assessment(
    organization_id: UUID,
    assessment_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*TRUST_READ_ROLES)),
) -> object:
    try:
        return trust_assessment_service.get(db, organization_id, assessment_id)
    except TrustNotFoundError as exc:
        _translate(exc)


@router.get(
    "/trust-assessments/{assessment_id}/rules",
    response_model=list[TrustRuleResultRead],
)
def list_trust_rule_results(
    organization_id: UUID,
    assessment_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*TRUST_READ_ROLES)),
) -> Sequence[object]:
    try:
        return trust_assessment_service.rule_results(db, organization_id, assessment_id)
    except TrustNotFoundError as exc:
        _translate(exc)


@router.get(
    "/trust-assessments/{assessment_id}/evidence",
    response_model=PaginatedTrustEvidence,
)
def list_trust_evidence(
    organization_id: UUID,
    assessment_id: UUID,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*TRUST_READ_ROLES)),
) -> PaginatedTrustEvidence:
    try:
        items, total = trust_assessment_service.evidence(
            db, organization_id, assessment_id, offset=offset, limit=limit
        )
    except TrustNotFoundError as exc:
        _translate(exc)
    return PaginatedTrustEvidence(
        items=[TrustEvidenceRead.model_validate(item) for item in items],
        offset=offset,
        limit=limit,
        returned=len(items),
        total=total,
    )


@router.get(
    "/trust-assessments/{assessment_id}/readiness",
    response_model=list[AnalyticalReadinessDecisionRead],
)
def list_analytical_readiness(
    organization_id: UUID,
    assessment_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*TRUST_READ_ROLES)),
) -> Sequence[object]:
    try:
        return trust_assessment_service.readiness(db, organization_id, assessment_id)
    except TrustNotFoundError as exc:
        _translate(exc)


@router.get(
    "/datasets/{dataset_id}/latest-trust-assessment",
    response_model=TrustAssessmentRead,
)
def latest_trust_assessment(
    organization_id: UUID,
    dataset_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*TRUST_READ_ROLES)),
) -> object:
    try:
        return trust_assessment_service.latest(db, organization_id, dataset_id)
    except TrustNotFoundError as exc:
        _translate(exc)
