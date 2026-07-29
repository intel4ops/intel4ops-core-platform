from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.entities import (
    MembershipRole,
    MembershipStatus,
    Organization,
    OrganizationMembership,
    utc_now,
)
from app.schemas.memberships import MembershipCreate


class MembershipNotFoundError(ValueError):
    pass


class MembershipOrganizationNotFoundError(ValueError):
    pass


class DuplicateMembershipError(ValueError):
    pass


class LastActiveOrganizationAdminError(ValueError):
    pass


class MembershipAuthorizationError(PermissionError):
    pass


class OrganizationMembershipService:
    def create(
        self,
        db: Session,
        organization_id: UUID,
        payload: MembershipCreate,
        invited_by_user_id: UUID,
    ) -> OrganizationMembership:
        if db.get(Organization, organization_id) is None:
            raise MembershipOrganizationNotFoundError("Organization not found")
        duplicate = db.scalar(
            select(OrganizationMembership.id).where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.user_id == payload.user_id,
            )
        )
        if duplicate is not None:
            raise DuplicateMembershipError("Organization membership already exists")
        membership = OrganizationMembership(
            organization_id=organization_id,
            user_id=payload.user_id,
            role=payload.role.value,
            status=payload.status.value,
            invited_by_user_id=invited_by_user_id,
            joined_at=utc_now() if payload.status is MembershipStatus.ACTIVE else None,
        )
        db.add(membership)
        self._commit(db, membership)
        return membership

    def list(
        self,
        db: Session,
        organization_id: UUID,
        *,
        role: MembershipRole | None = None,
        status: MembershipStatus | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[OrganizationMembership]:
        statement = select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id
        )
        if role is not None:
            statement = statement.where(OrganizationMembership.role == role.value)
        if status is not None:
            statement = statement.where(OrganizationMembership.status == status.value)
        statement = (
            statement.order_by(OrganizationMembership.created_at).offset(offset).limit(limit)
        )
        return list(db.scalars(statement).all())

    def get(
        self,
        db: Session,
        organization_id: UUID,
        membership_id: UUID,
        *,
        for_update: bool = False,
    ) -> OrganizationMembership:
        statement = select(OrganizationMembership).where(
            OrganizationMembership.id == membership_id,
            OrganizationMembership.organization_id == organization_id,
        )
        if for_update:
            statement = statement.with_for_update()
        membership = db.scalar(statement)
        if membership is None:
            raise MembershipNotFoundError("Organization membership not found")
        return membership

    def update_role(
        self,
        db: Session,
        organization_id: UUID,
        membership_id: UUID,
        role: MembershipRole,
    ) -> OrganizationMembership:
        self._lock_organization(db, organization_id)
        membership = self.get(db, organization_id, membership_id, for_update=True)
        if (
            membership.role == MembershipRole.ORGANIZATION_ADMIN.value
            and role is not MembershipRole.ORGANIZATION_ADMIN
        ):
            self._protect_last_active_admin(db, membership)
        membership.role = role.value
        self._commit(db, membership)
        return membership

    def activate(
        self, db: Session, organization_id: UUID, membership_id: UUID
    ) -> OrganizationMembership:
        membership = self.get(db, organization_id, membership_id, for_update=True)
        membership.status = MembershipStatus.ACTIVE.value
        if membership.joined_at is None:
            membership.joined_at = utc_now()
        self._commit(db, membership)
        return membership

    def suspend(
        self, db: Session, organization_id: UUID, membership_id: UUID
    ) -> OrganizationMembership:
        self._lock_organization(db, organization_id)
        membership = self.get(db, organization_id, membership_id, for_update=True)
        self._protect_last_active_admin(db, membership)
        membership.status = MembershipStatus.SUSPENDED.value
        self._commit(db, membership)
        return membership

    def revoke(
        self, db: Session, organization_id: UUID, membership_id: UUID
    ) -> OrganizationMembership:
        self._lock_organization(db, organization_id)
        membership = self.get(db, organization_id, membership_id, for_update=True)
        self._protect_last_active_admin(db, membership)
        membership.status = MembershipStatus.REVOKED.value
        self._commit(db, membership)
        return membership

    def require_active_member(
        self, db: Session, organization_id: UUID, user_id: UUID
    ) -> OrganizationMembership:
        membership = db.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.status == MembershipStatus.ACTIVE.value,
            )
        )
        if membership is None:
            raise MembershipAuthorizationError("Active organization membership required")
        return membership

    def require_roles(
        self,
        db: Session,
        organization_id: UUID,
        user_id: UUID,
        allowed_roles: set[MembershipRole],
    ) -> OrganizationMembership:
        membership = self.require_active_member(db, organization_id, user_id)
        if membership.role not in {role.value for role in allowed_roles}:
            raise MembershipAuthorizationError("Membership role is not permitted")
        return membership

    def _protect_last_active_admin(self, db: Session, membership: OrganizationMembership) -> None:
        if (
            membership.role != MembershipRole.ORGANIZATION_ADMIN.value
            or membership.status != MembershipStatus.ACTIVE.value
        ):
            return
        active_admin_count = db.scalar(
            select(func.count())
            .select_from(OrganizationMembership)
            .where(
                OrganizationMembership.organization_id == membership.organization_id,
                OrganizationMembership.role == MembershipRole.ORGANIZATION_ADMIN.value,
                OrganizationMembership.status == MembershipStatus.ACTIVE.value,
            )
        )
        if active_admin_count == 1:
            raise LastActiveOrganizationAdminError(
                "The last active organization administrator cannot be changed"
            )

    @staticmethod
    def _lock_organization(db: Session, organization_id: UUID) -> None:
        organization = db.scalar(
            select(Organization).where(Organization.id == organization_id).with_for_update()
        )
        if organization is None:
            raise MembershipOrganizationNotFoundError("Organization not found")

    @staticmethod
    def _commit(db: Session, membership: OrganizationMembership) -> None:
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise DuplicateMembershipError("Organization membership already exists") from exc
        db.refresh(membership)


membership_service = OrganizationMembershipService()
