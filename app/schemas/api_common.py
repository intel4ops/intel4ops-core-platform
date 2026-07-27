from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class RequestContext(BaseModel):
    request_id: str
    correlation_id: str
    organization_id: UUID
    user_id: UUID
    actor_type: str = "user"
    client_code: str
    roles: list[str]
    subscription_id: UUID | None = None
    plan_version_id: UUID | None = None
    locale: str = "en-US"
    requested_currency: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class FieldError(BaseModel):
    field: str
    message: str


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str
    details: dict[str, object] = Field(default_factory=dict)
    field_errors: list[FieldError] = Field(default_factory=list)


class ErrorEnvelope(BaseModel):
    error: ErrorBody


class PageQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)
    sort_direction: Literal["asc", "desc"] = "desc"


def new_request_id() -> str:
    return str(uuid4())
