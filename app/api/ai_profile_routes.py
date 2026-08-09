from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.authorization import OrganizationAccess
from app.auth.commercial import require_commercial_entitlement
from app.auth.permissions import (
    FINDING_READ_ROLES,
    INTELLIGENCE_EXECUTION_ROLES,
    ORGANIZATION_ADMIN_ROLES,
)
from app.db.session import get_db
from app.models.ai_profile import AIOperationalProfile, AIProfileInference
from app.schemas.ai_profile import (
    AIOperationalProfileCreate,
    AIOperationalProfileRead,
    AIProfileDecision,
    AIProfileInferenceRead,
)
from app.services.ai_operational_profile_service import (
    AIOperationalProfileServiceError,
    ai_operational_profile_service,
)

router = APIRouter(
    prefix="/api/v1/organizations/{organization_id}/operational-profiles",
    tags=["ai-operational-profile"],
)


def _raise(exc: AIOperationalProfileServiceError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status,
        detail={"code": exc.code, "message": str(exc)},
    ) from exc


def _profile_response(
    profile: AIOperationalProfile, inferences: list[AIProfileInference]
) -> AIOperationalProfileRead:
    payload = AIOperationalProfileRead.model_validate(profile)
    return payload.model_copy(
        update={"inferences": [AIProfileInferenceRead.model_validate(row) for row in inferences]}
    )


@router.post("", response_model=AIOperationalProfileRead, status_code=201)
def create_operational_profile(
    organization_id: UUID,
    payload: AIOperationalProfileCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(
        require_commercial_entitlement("intelligence.findings", *INTELLIGENCE_EXECUTION_ROLES)
    ),
) -> AIOperationalProfileRead:
    try:
        profile = ai_operational_profile_service.create(
            db,
            organization_id,
            access.user.user_id,
            payload.idempotency_key,
        )
        stored, inferences = ai_operational_profile_service.get(db, organization_id, profile.id)
    except AIOperationalProfileServiceError as exc:
        _raise(exc)
    return _profile_response(stored, inferences)


@router.get("/{profile_id}", response_model=AIOperationalProfileRead)
def read_operational_profile(
    organization_id: UUID,
    profile_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(
        require_commercial_entitlement("intelligence.findings", *FINDING_READ_ROLES)
    ),
) -> AIOperationalProfileRead:
    try:
        profile, inferences = ai_operational_profile_service.get(db, organization_id, profile_id)
    except AIOperationalProfileServiceError as exc:
        _raise(exc)
    return _profile_response(profile, inferences)


@router.post(
    "/{profile_id}/inferences/{inference_id}/confirm",
    response_model=AIProfileInferenceRead,
)
def decide_operational_profile_inference(
    organization_id: UUID,
    profile_id: UUID,
    inference_id: UUID,
    payload: AIProfileDecision,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(
        require_commercial_entitlement("intelligence.findings", *ORGANIZATION_ADMIN_ROLES)
    ),
) -> AIProfileInference:
    try:
        return ai_operational_profile_service.decide(
            db,
            organization_id,
            profile_id,
            inference_id,
            access.user.user_id,
            payload,
        )
    except AIOperationalProfileServiceError as exc:
        _raise(exc)


@router.post(
    "/{profile_id}/inferences/{inference_id}/reject",
    response_model=AIProfileInferenceRead,
)
def reject_operational_profile_inference(
    organization_id: UUID,
    profile_id: UUID,
    inference_id: UUID,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(
        require_commercial_entitlement("intelligence.findings", *ORGANIZATION_ADMIN_ROLES)
    ),
) -> AIProfileInference:
    try:
        return ai_operational_profile_service.reject(
            db,
            organization_id,
            profile_id,
            inference_id,
            access.user.user_id,
        )
    except AIOperationalProfileServiceError as exc:
        _raise(exc)
