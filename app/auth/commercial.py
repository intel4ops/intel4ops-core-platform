from collections.abc import Callable
from uuid import UUID

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.authorization import OrganizationAccess, require_organization_roles
from app.db.session import get_db
from app.models.entities import MembershipRole
from app.services.commercial_service import CommercialServiceError, entitlement_service


def require_commercial_entitlement(
    entitlement_key: str, *roles: MembershipRole
) -> Callable[..., OrganizationAccess]:
    authorization = require_organization_roles(*roles)

    def dependency(
        organization_id: UUID,
        db: Session = Depends(get_db),
        access: OrganizationAccess = Depends(authorization),
    ) -> OrganizationAccess:
        if access.user.is_platform_admin:
            return access
        try:
            entitlement_service.require(db, organization_id, entitlement_key)
        except CommercialServiceError as exc:
            raise HTTPException(
                status_code=exc.status,
                detail={"code": exc.code, "message": str(exc)},
            ) from exc
        return access

    return dependency
