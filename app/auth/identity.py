from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from fastapi import HTTPException, status


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: UUID
    is_platform_admin: bool = False


class IdentityProvider(Protocol):
    def authenticate(self) -> AuthenticatedUser: ...


def get_current_user() -> AuthenticatedUser:
    """Fail closed until a production identity provider is configured."""
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication is not configured",
    )
