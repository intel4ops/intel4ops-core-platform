from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.authorization import OrganizationAccess
from app.auth.commercial import require_commercial_entitlement
from app.auth.permissions import ORGANIZATION_READ_ROLES
from app.db.session import get_db
from app.models.commercial import Subscription
from app.models.gateway import ApplicationClient
from app.schemas.api_common import RequestContext
from app.services.api_gateway_service import api_gateway_service

router = APIRouter(
    prefix="/api/v1/organizations/{organization_id}/gateway", tags=["Application Gateway"]
)


@router.get("/context", response_model=RequestContext)
def context(
    organization_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(
        require_commercial_entitlement("commercial.api_access", *ORGANIZATION_READ_ROLES)
    ),
) -> object:
    transport = request.state.gateway_transport_context
    client = db.scalar(
        select(ApplicationClient).where(
            ApplicationClient.client_code == transport["client_code"],
            ApplicationClient.status == "active",
        )
    )
    if client is None:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "CLIENT_NOT_REGISTERED",
                "message": "Application client is not registered",
            },
        )
    subscription = db.scalar(
        select(Subscription)
        .where(Subscription.organization_id == organization_id)
        .order_by(Subscription.created_at.desc())
    )
    roles = [access.membership.role] if access.membership else ["platform_admin"]
    resolved = RequestContext(
        **transport,
        organization_id=organization_id,
        user_id=access.user.user_id,
        roles=roles,
        subscription_id=subscription.id if subscription else None,
        plan_version_id=subscription.plan_version_id if subscription else None,
    )
    api_gateway_service.audit(db, resolved, "gateway.context")
    return resolved
