from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.identity import AuthenticatedUser
from app.models.commercial import (
    Entitlement,
    IndustryPackAssignment,
    IndustryPackDefinition,
    Plan,
    PlanVersion,
    Subscription,
)
from app.models.entities import (
    MembershipRole,
    MembershipStatus,
    Organization,
    OrganizationMembership,
    utc_now,
)
from app.schemas.access import (
    AccessContextRead,
    AccessSummaryRead,
    CurrentIdentityRead,
    MembershipSummary,
    OrganizationSummary,
)
from app.schemas.contracts import OrganizationCreate
from app.services.invitation_service import record_access_audit_event

# Descriptive-only mapping of role -> UI-facing capability labels. This does
# not enforce anything; enforcement continues to run entirely through
# require_organization_roles / require_commercial_entitlement.
_PERMITTED_ACTIONS: dict[str, tuple[str, ...]] = {
    MembershipRole.ORGANIZATION_ADMIN.value: (
        "invite_members",
        "manage_roles",
        "manage_organization",
        "view_workspace",
    ),
    MembershipRole.ANALYST.value: ("view_workspace", "analyze"),
    MembershipRole.OPERATOR.value: ("view_workspace", "operate"),
    MembershipRole.RECOVERY_MANAGER.value: ("view_workspace", "manage_recovery"),
    MembershipRole.VIEWER.value: ("view_workspace",),
}


class AccessContextServiceError(ValueError):
    def __init__(self, message: str, *, code: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


class OrganizationProvisioningError(ValueError):
    pass


def create_organization_with_owner(
    db: Session, payload: OrganizationCreate, creator_user_id: UUID
) -> Organization:
    """Atomically create an organization and grant its creator an active
    organization_admin membership. Constructs both rows directly (rather than
    composing OrganizationService.create()/MembershipService.create(), which
    each commit independently) so a single db.commit() covers both -- if
    either insert fails, neither is left partially provisioned."""
    if db.scalar(select(Organization.id).where(Organization.slug == payload.slug)):
        raise OrganizationProvisioningError("Organization slug already exists")
    organization = Organization(**payload.model_dump())
    db.add(organization)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise OrganizationProvisioningError("Organization slug already exists") from exc
    membership = OrganizationMembership(
        organization_id=organization.id,
        user_id=creator_user_id,
        role=MembershipRole.ORGANIZATION_ADMIN.value,
        status=MembershipStatus.ACTIVE.value,
        joined_at=utc_now(),
    )
    db.add(membership)
    db.flush()
    record_access_audit_event(
        db,
        organization.id,
        "organization_created",
        "organization",
        organization.id,
        creator_user_id,
        "Organization created",
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise OrganizationProvisioningError("Organization slug already exists") from exc
    db.refresh(organization)
    return organization


def _membership_to_summary(membership: OrganizationMembership) -> MembershipSummary:
    return MembershipSummary(
        organization=OrganizationSummary.model_validate(membership.organization),
        role=MembershipRole(membership.role),
        status=membership.status,
    )


def get_current_identity(db: Session, user: AuthenticatedUser) -> CurrentIdentityRead:
    memberships = list(
        db.scalars(
            select(OrganizationMembership).where(
                OrganizationMembership.user_id == user.user_id,
                OrganizationMembership.status == MembershipStatus.ACTIVE.value,
            )
        )
    )
    return CurrentIdentityRead(
        user_id=user.user_id,
        is_platform_admin=user.is_platform_admin,
        memberships=[_membership_to_summary(m) for m in memberships],
    )


def _resolve_entitlement_summary(db: Session, organization_id: UUID) -> dict[str, object]:
    entitlements = list(
        db.scalars(
            select(Entitlement).where(
                Entitlement.organization_id == organization_id,
                Entitlement.enabled.is_(True),
            )
        )
    )
    return {"enabled_entitlements": sorted({item.entitlement_key for item in entitlements})}


def get_access_context(
    db: Session, user: AuthenticatedUser, organization_id: UUID | None
) -> AccessContextRead:
    memberships = list(
        db.scalars(
            select(OrganizationMembership).where(
                OrganizationMembership.user_id == user.user_id,
            )
        )
    )
    active_memberships = [m for m in memberships if m.status == MembershipStatus.ACTIVE.value]

    membership: OrganizationMembership | None
    if organization_id is None:
        if not active_memberships:
            return AccessContextRead(state="no_membership", user_id=user.user_id)
        if len(active_memberships) > 1:
            return AccessContextRead(state="multiple_organizations", user_id=user.user_id)
        membership = active_memberships[0]
    else:
        membership = next(
            (m for m in memberships if m.organization_id == organization_id), None
        )
        if membership is None:
            return AccessContextRead(state="no_membership", user_id=user.user_id)
        if membership.status == MembershipStatus.REVOKED.value:
            return AccessContextRead(state="revoked_membership", user_id=user.user_id)
        if membership.status == MembershipStatus.SUSPENDED.value:
            return AccessContextRead(state="suspended_organization", user_id=user.user_id)
        if membership.status == MembershipStatus.INVITED.value:
            return AccessContextRead(state="pending_invitation", user_id=user.user_id)

    organization = db.get(Organization, membership.organization_id)
    if organization is None or organization.status != "active":
        return AccessContextRead(
            state="suspended_organization",
            user_id=user.user_id,
            organization=(
                OrganizationSummary.model_validate(organization) if organization else None
            ),
        )
    return AccessContextRead(
        state="active",
        user_id=user.user_id,
        organization=OrganizationSummary.model_validate(organization),
        role=MembershipRole(membership.role),
        membership_status=membership.status,
        permitted_actions=list(_PERMITTED_ACTIONS.get(membership.role, ())),
        entitlement_summary=_resolve_entitlement_summary(db, organization.id),
    )


def get_access_summary(db: Session, organization_id: UUID) -> AccessSummaryRead:
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise AccessContextServiceError(
            "Organization not found", code="organization_not_found", status=404
        )
    subscription = db.scalar(
        select(Subscription)
        .where(Subscription.organization_id == organization_id)
        .order_by(Subscription.starts_at.desc())
    )
    plan_code: str | None = None
    if subscription is not None:
        version = db.get(PlanVersion, subscription.plan_version_id)
        if version is not None:
            plan = db.get(Plan, version.plan_id)
            plan_code = plan.code if plan is not None else None
    entitlements = list(
        db.scalars(
            select(Entitlement).where(
                Entitlement.organization_id == organization_id,
                Entitlement.enabled.is_(True),
            )
        )
    )
    pack_codes = list(
        db.scalars(
            select(IndustryPackDefinition.code)
            .join(
                IndustryPackAssignment,
                IndustryPackAssignment.pack_id == IndustryPackDefinition.id,
            )
            .where(
                IndustryPackAssignment.organization_id == organization_id,
                IndustryPackAssignment.status == "active",
            )
        )
    )
    return AccessSummaryRead(
        organization_id=organization_id,
        organization_status=organization.status,
        plan_code=plan_code,
        subscription_status=subscription.status if subscription is not None else None,
        enabled_entitlements=sorted({item.entitlement_key for item in entitlements}),
        industry_pack_codes=sorted(pack_codes),
    )
