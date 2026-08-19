"""P3.xxA.2 pilot auth bridge.

Temporary, environment-gated bearer-token identity used only to unblock a
pilot deployment (e.g. SOTRA) before real platform-admin provisioning ships
(see the is_platform_admin comment on OIDCIdentityProvider.authenticate in
app/auth/identity.py). Delete this module and its call site in
get_current_user() once that ships.

This is not a general-purpose auth mechanism and never activates unless
ALL of the following hold:
  - settings.app_env != "production" -- checked unconditionally, first, and
    independent of pilot_auth_enabled, so a production deployment can never
    reach the token comparison even if pilot vars are misconfigured.
  - settings.pilot_auth_enabled is True -- disabled by default.
  - both pilot_auth_token and pilot_user_id are configured -- no
    source-code secret; both come from deployment environment
    configuration, and there is no default for either.
  - the request's Authorization bearer token matches pilot_auth_token
    exactly, via a constant-time compare -- never a wildcard/anonymous
    bypass. Any request that doesn't match (wrong token, missing header,
    pilot mode inapplicable) returns None so the caller falls through to
    unmodified OIDC verification.
Every successful activation is logged at WARNING (never the token itself)
so pilot-identity usage stays audit-visible.
"""

import hmac
import logging
from uuid import UUID

from app.core.config import Settings

logger = logging.getLogger("app.auth.pilot_bridge")


def resolve_pilot_identity(
    settings: Settings, authorization: str | None
) -> tuple[UUID, bool] | None:
    """Return (user_id, is_platform_admin) for a matching pilot bearer
    token, or None if the pilot bridge does not apply to this request.
    """
    if settings.app_env == "production":
        return None
    if not settings.pilot_auth_enabled:
        return None
    token = settings.pilot_auth_token
    user_id = settings.pilot_user_id
    if not token or user_id is None:
        return None
    if not authorization:
        return None
    scheme, _, candidate = authorization.partition(" ")
    candidate = candidate.strip()
    if scheme.lower() != "bearer" or not candidate:
        return None
    if not hmac.compare_digest(candidate, token):
        return None
    logger.warning(
        "pilot_auth_bridge_activated user_id=%s is_platform_admin=%s",
        user_id,
        settings.pilot_platform_admin,
    )
    return user_id, settings.pilot_platform_admin
