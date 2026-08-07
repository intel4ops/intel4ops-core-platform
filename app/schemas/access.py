from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.entities import MembershipRole


class InvitationCreate(BaseModel):
    email: EmailStr
    role: MembershipRole


class InvitationRead(BaseModel):
    id: UUID
    organization_id: UUID
    email: str
    role: MembershipRole
    status: str
    invited_by_user_id: UUID
    expires_at: datetime
    accepted_at: datetime | None
    accepted_by_user_id: UUID | None
    resulting_membership_id: UUID | None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class InvitationCreateResult(BaseModel):
    invitation: InvitationRead
    token: str = Field(
        description=(
            "Raw invitation token, returned exactly once at creation time. "
            "Never persisted or retrievable again; deliver it to the invitee "
            "through your own controlled-beta channel."
        )
    )


class InvitationAccept(BaseModel):
    token: str = Field(min_length=32)


class OrganizationSummary(BaseModel):
    id: UUID
    name: str
    slug: str
    status: str
    model_config = ConfigDict(from_attributes=True)


class MembershipSummary(BaseModel):
    organization: OrganizationSummary
    role: MembershipRole
    status: str


class CurrentIdentityRead(BaseModel):
    user_id: UUID
    is_platform_admin: bool
    memberships: list[MembershipSummary]


class AccessContextState(BaseModel):
    """One of: active, no_membership, multiple_organizations,
    suspended_organization, revoked_membership, session_expired."""

    state: str
    detail: str | None = None


class AccessContextRead(BaseModel):
    state: str
    user_id: UUID
    organization: OrganizationSummary | None = None
    role: MembershipRole | None = None
    membership_status: str | None = None
    permitted_actions: list[str] = Field(default_factory=list)
    entitlement_summary: dict[str, object] | None = None


class AccessSummaryRead(BaseModel):
    organization_id: UUID
    organization_status: str
    plan_code: str | None
    subscription_status: str | None
    enabled_entitlements: list[str]
    industry_pack_codes: list[str]
