from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.authorization import OrganizationAccess, require_organization_roles
from app.auth.permissions import SEMANTIC_REVIEW_ROLES
from app.db.session import get_db
from app.schemas.semantic_review import (
    EffectiveDecisionRead,
    EffectiveFieldRead,
    MachineProposalRead,
    ReviewHistoryEntryRead,
    ReviewHistoryRead,
    ReviewItemDetailRead,
    ReviewQueueItemRead,
    ReviewQueueRead,
    RunEffectiveDecisionsRead,
    SemanticDecisionVersionRead,
    SemanticReviewRead,
    SubmitReviewRequest,
    SubmitReviewResponse,
)
from app.services.semantic_review_service import (
    SemanticReviewServiceError,
    semantic_review_service,
)

router = APIRouter(prefix="/api/v1/organizations/{organization_id}/analysis-cases")


def _raise(exc: Exception, default_status: int = 400) -> NoReturn:
    status_code = getattr(exc, "status", default_status)
    code = getattr(exc, "code", "semantic_review_error")
    detail = {"code": code, "message": str(exc)}
    raise HTTPException(status_code=status_code, detail=detail) from exc


def _machine_proposal_read(decision: object) -> MachineProposalRead:
    return MachineProposalRead.model_validate(decision, from_attributes=True)


@router.get(
    "/{case_id}/semantic/review-queue",
    response_model=ReviewQueueRead,
)
def list_review_queue(
    organization_id: UUID,
    case_id: UUID,
    run_id: UUID | None = None,
    group: str | None = None,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*SEMANTIC_REVIEW_ROLES)),
) -> object:
    try:
        items = semantic_review_service.list_review_queue(
            db, organization_id, case_id, run_id, group
        )
    except SemanticReviewServiceError as exc:
        _raise(exc)
    return ReviewQueueRead(
        analysis_case_id=case_id,
        run_id=run_id,
        items=[
            ReviewQueueItemRead(
                decision_id=item.decision.id,
                analysis_case_dataset_id=item.decision.analysis_case_dataset_id,
                dataset_label=item.dataset_label,
                source_field=item.decision.source_field,
                machine_selected_concept=item.decision.selected_concept,
                machine_confidence=item.decision.confidence,
                machine_status=item.decision.status,
                alternative_candidates=item.decision.alternative_candidates,
                evidence_summary=item.decision.evidence_summary,
                current_version=item.latest_version.version_number if item.latest_version else None,
                effective_state=item.latest_version.effective_status
                if item.latest_version
                else item.decision.status,
                group=item.group.value,
            )
            for item in items
        ],
    )


@router.get(
    "/{case_id}/semantic/decisions/{decision_id}/review",
    response_model=ReviewItemDetailRead,
)
def get_review_item(
    organization_id: UUID,
    case_id: UUID,
    decision_id: UUID,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*SEMANTIC_REVIEW_ROLES)),
) -> object:
    try:
        decision, latest_version, effective = semantic_review_service.get_review_item(
            db, organization_id, decision_id
        )
    except SemanticReviewServiceError as exc:
        _raise(exc)
    return ReviewItemDetailRead(
        decision_id=decision.id,
        machine_proposal=_machine_proposal_read(decision),
        effective_decision=EffectiveDecisionRead(**effective.__dict__),
        current_version=latest_version.version_number if latest_version else 0,
    )


@router.post(
    "/{case_id}/semantic/decisions/{decision_id}/review",
    response_model=SubmitReviewResponse,
    status_code=status.HTTP_201_CREATED,
)
def submit_review(
    organization_id: UUID,
    case_id: UUID,
    decision_id: UUID,
    payload: SubmitReviewRequest,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*SEMANTIC_REVIEW_ROLES)),
) -> object:
    reviewer_role = access.membership.role if access.membership else "platform_admin"
    try:
        review, version = semantic_review_service.submit_review(
            db,
            organization_id,
            decision_id,
            action=payload.action,
            corrected_concept=payload.corrected_concept,
            notes=payload.notes,
            expected_version=payload.expected_version,
            reviewer_user_id=access.user.user_id,
            reviewer_role=reviewer_role,
        )
    except SemanticReviewServiceError as exc:
        _raise(exc)
    _, _, effective = semantic_review_service.get_review_item(db, organization_id, decision_id)
    return SubmitReviewResponse(
        review=SemanticReviewRead.model_validate(review, from_attributes=True),
        version=SemanticDecisionVersionRead.model_validate(version, from_attributes=True),
        effective_decision=EffectiveDecisionRead(**effective.__dict__),
    )


@router.get(
    "/{case_id}/semantic/decisions/{decision_id}/history",
    response_model=ReviewHistoryRead,
)
def get_review_history(
    organization_id: UUID,
    case_id: UUID,
    decision_id: UUID,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*SEMANTIC_REVIEW_ROLES)),
) -> object:
    try:
        decision, _, _ = semantic_review_service.get_review_item(db, organization_id, decision_id)
        entries = semantic_review_service.get_history(db, organization_id, decision_id)
    except SemanticReviewServiceError as exc:
        _raise(exc)
    return ReviewHistoryRead(
        decision_id=decision_id,
        machine_proposal=_machine_proposal_read(decision),
        entries=[
            ReviewHistoryEntryRead(
                review=SemanticReviewRead.model_validate(entry.review, from_attributes=True),
                version=SemanticDecisionVersionRead.model_validate(
                    entry.version, from_attributes=True
                ),
            )
            for entry in entries
        ],
    )


@router.get(
    "/{case_id}/semantic/effective",
    response_model=RunEffectiveDecisionsRead,
)
def get_effective_for_run(
    organization_id: UUID,
    case_id: UUID,
    run_id: UUID,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*SEMANTIC_REVIEW_ROLES)),
) -> object:
    try:
        results = semantic_review_service.get_effective_for_run(
            db, organization_id, case_id, run_id
        )
    except SemanticReviewServiceError as exc:
        _raise(exc)
    return RunEffectiveDecisionsRead(
        analysis_case_id=case_id,
        run_id=run_id,
        fields=[
            EffectiveFieldRead(
                decision_id=decision.id,
                analysis_case_dataset_id=decision.analysis_case_dataset_id,
                source_field=decision.source_field,
                effective_decision=EffectiveDecisionRead(**effective.__dict__),
            )
            for decision, effective in results
        ],
    )
