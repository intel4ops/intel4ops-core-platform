from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.auth.authorization import OrganizationAccess
from app.auth.commercial import require_commercial_entitlement
from app.auth.permissions import FINDING_ADMIN_ROLES, FINDING_READ_ROLES, FINDING_REVIEW_ROLES
from app.db.session import get_db
from app.schemas.knowledge_pack import (
    KnowledgePackCreate,
    KnowledgePackLearningAdd,
    KnowledgePackPage,
    KnowledgePackRead,
    KnowledgePackTransition,
    KnowledgePackVersionCreate,
    KnowledgePackVersionRead,
)
from app.services.knowledge_pack_service import (
    KnowledgePackServiceError,
    knowledge_pack_service,
)

router = APIRouter(
    prefix="/api/v1/organizations/{organization_id}/knowledge-packs",
    tags=["knowledge-packs"],
)


def _error(exc: KnowledgePackServiceError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status, detail={"code": exc.code, "message": str(exc)}
    ) from exc


def _role(access: OrganizationAccess) -> str:
    return "platform_admin" if access.membership is None else str(access.membership.role)


@router.get("", response_model=KnowledgePackPage)
def list_knowledge_packs(
    organization_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    lifecycle: str | None = None,
    provenance: str | None = None,
    industry: str | None = None,
    domain: str | None = None,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(
        require_commercial_entitlement("intelligence.findings", *FINDING_READ_ROLES)
    ),
) -> KnowledgePackPage:
    return knowledge_pack_service.list_packs(
        db,
        organization_id,
        page=page,
        page_size=page_size,
        lifecycle=lifecycle,
        provenance=provenance,
        industry=industry,
        domain=domain,
    )


@router.post("", response_model=KnowledgePackRead, status_code=201)
def create_knowledge_pack(
    organization_id: UUID,
    payload: KnowledgePackCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(
        require_commercial_entitlement("intelligence.findings", *FINDING_REVIEW_ROLES)
    ),
) -> KnowledgePackRead:
    try:
        return knowledge_pack_service.create(
            db, organization_id, payload, access.user.user_id, _role(access)
        )
    except KnowledgePackServiceError as exc:
        _error(exc)


@router.get("/{pack_id}", response_model=KnowledgePackRead)
def get_knowledge_pack(
    organization_id: UUID,
    pack_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(
        require_commercial_entitlement("intelligence.findings", *FINDING_READ_ROLES)
    ),
) -> KnowledgePackRead:
    try:
        return knowledge_pack_service.get(db, organization_id, pack_id)
    except KnowledgePackServiceError as exc:
        _error(exc)


@router.get("/{pack_id}/versions/{version_id}", response_model=KnowledgePackVersionRead)
def get_knowledge_pack_version(
    organization_id: UUID,
    pack_id: UUID,
    version_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(
        require_commercial_entitlement("intelligence.findings", *FINDING_READ_ROLES)
    ),
) -> KnowledgePackVersionRead:
    try:
        return knowledge_pack_service.get_version(db, organization_id, pack_id, version_id)
    except KnowledgePackServiceError as exc:
        _error(exc)


@router.post("/{pack_id}/versions", response_model=KnowledgePackRead, status_code=201)
def create_knowledge_pack_version(
    organization_id: UUID,
    pack_id: UUID,
    payload: KnowledgePackVersionCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(
        require_commercial_entitlement("intelligence.findings", *FINDING_REVIEW_ROLES)
    ),
) -> KnowledgePackRead:
    try:
        return knowledge_pack_service.create_version(
            db, organization_id, pack_id, payload, access.user.user_id, _role(access)
        )
    except KnowledgePackServiceError as exc:
        _error(exc)


@router.post(
    "/{pack_id}/versions/{version_id}/learning",
    response_model=KnowledgePackVersionRead,
    status_code=201,
)
def add_pack_learning(
    organization_id: UUID,
    pack_id: UUID,
    version_id: UUID,
    payload: KnowledgePackLearningAdd,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(
        require_commercial_entitlement("intelligence.findings", *FINDING_REVIEW_ROLES)
    ),
) -> KnowledgePackVersionRead:
    try:
        return knowledge_pack_service.add_learning(
            db,
            organization_id,
            pack_id,
            version_id,
            payload,
            access.user.user_id,
            _role(access),
        )
    except KnowledgePackServiceError as exc:
        _error(exc)


@router.delete("/{pack_id}/versions/{version_id}/learning/{learning_id}", status_code=204)
def remove_pack_learning(
    organization_id: UUID,
    pack_id: UUID,
    version_id: UUID,
    learning_id: UUID,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(
        require_commercial_entitlement("intelligence.findings", *FINDING_REVIEW_ROLES)
    ),
) -> Response:
    try:
        knowledge_pack_service.remove_learning(
            db,
            organization_id,
            pack_id,
            version_id,
            learning_id,
            access.user.user_id,
            _role(access),
        )
    except KnowledgePackServiceError as exc:
        _error(exc)
    return Response(status_code=204)


def _transition(
    db: Session,
    organization_id: UUID,
    pack_id: UUID,
    version_id: UUID,
    command: str,
    payload: KnowledgePackTransition,
    access: OrganizationAccess,
) -> KnowledgePackRead:
    try:
        return knowledge_pack_service.transition(
            db,
            organization_id,
            pack_id,
            version_id,
            command,
            payload.rationale,
            access.user.user_id,
            _role(access),
        )
    except KnowledgePackServiceError as exc:
        _error(exc)


@router.post("/{pack_id}/versions/{version_id}/submit", response_model=KnowledgePackRead)
def submit_knowledge_pack_version(
    organization_id: UUID,
    pack_id: UUID,
    version_id: UUID,
    payload: KnowledgePackTransition,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(
        require_commercial_entitlement("intelligence.findings", *FINDING_REVIEW_ROLES)
    ),
) -> KnowledgePackRead:
    return _transition(db, organization_id, pack_id, version_id, "submit", payload, access)


@router.post("/{pack_id}/versions/{version_id}/{command}", response_model=KnowledgePackRead)
def govern_knowledge_pack_version(
    organization_id: UUID,
    pack_id: UUID,
    version_id: UUID,
    command: str,
    payload: KnowledgePackTransition,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(
        require_commercial_entitlement("intelligence.findings", *FINDING_ADMIN_ROLES)
    ),
) -> KnowledgePackRead:
    if command not in {"approve", "reject", "retire"}:
        raise HTTPException(
            status_code=404,
            detail={"code": "PACK_COMMAND_NOT_FOUND", "message": "Pack command not found"},
        )
    return _transition(db, organization_id, pack_id, version_id, command, payload, access)
