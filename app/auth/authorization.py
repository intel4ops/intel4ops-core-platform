from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.identity import AuthenticatedUser, get_current_user
from app.db.session import get_db
from app.models.entities import MembershipRole, OrganizationMembership
from app.services.membership_service import MembershipAuthorizationError, membership_service


@dataclass(frozen=True)
class OrganizationAccess:
    user: AuthenticatedUser
    membership: OrganizationMembership | None


def require_organization_roles(
    *allowed_roles: MembershipRole,
) -> Callable[..., OrganizationAccess]:
    def dependency(
        organization_id: UUID,
        db: Session = Depends(get_db),
        current_user: AuthenticatedUser = Depends(get_current_user),
    ) -> OrganizationAccess:
        if current_user.is_platform_admin:
            return OrganizationAccess(user=current_user, membership=None)
        try:
            membership = membership_service.require_roles(
                db,
                organization_id=organization_id,
                user_id=current_user.user_id,
                allowed_roles=set(allowed_roles),
            )
        except MembershipAuthorizationError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Organization access denied",
            ) from exc
        return OrganizationAccess(user=current_user, membership=membership)

    return dependency


def require_platform_admin(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> AuthenticatedUser:
    if not current_user.is_platform_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform administrator access required",
        )
    return current_user
