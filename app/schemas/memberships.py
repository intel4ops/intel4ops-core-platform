from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.entities import MembershipRole, MembershipStatus


class MembershipCreate(BaseModel):
    user_id: UUID
    role: MembershipRole
    status: MembershipStatus = MembershipStatus.INVITED


class MembershipRoleUpdate(BaseModel):
    role: MembershipRole


class MembershipRead(BaseModel):
    id: UUID
    organization_id: UUID
    user_id: UUID
    role: MembershipRole
    status: MembershipStatus
    invited_by_user_id: UUID | None
    joined_at: datetime | None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
