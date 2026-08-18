from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol
from uuid import UUID, uuid5

import jwt
from fastapi import Header, HTTPException, status
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError, PyJWKClientError, PyJWTError

from app.core.config import get_settings

# Governed namespace for deriving Intel4Ops user_id values from verified OIDC
# identities. Fixed and never to be changed: doing so would re-derive a
# different user_id for every existing customer identity and break
# membership identity continuity across the platform.
GOVERNED_INTEL4OPS_IDENTITY_NAMESPACE = UUID("6f6e5f4a-9b1d-4c3e-8a2f-2f7b6e1d5c4a")


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: UUID
    is_platform_admin: bool = False
    # Recipient-binding evidence only (CMVP-01 invitation acceptance) --
    # never the durable identity key. user_id (derived from issuer+subject
    # above) remains the only identifier membership rows are keyed on.
    # Populated from the OIDC provider's namespaced access-token claims
    # (see _EMAIL_CLAIM/_EMAIL_VERIFIED_CLAIM below); absent for any token
    # that doesn't carry them.
    email: str | None = None
    email_verified: bool = False


class IdentityProvider(Protocol):
    def authenticate(self, authorization: str | None) -> AuthenticatedUser: ...


class AuthenticationError(HTTPException):
    # FastAPI's HTTPException accepts Any for detail; Starlette's base class
    # narrows the attribute's declared type to str, which this class doesn't
    # honor by design (detail is always the structured {code, message} dict
    # below).
    detail: dict[str, str]  # type: ignore[assignment]

    def __init__(self, code: str, http_status: int, message: str) -> None:
        super().__init__(status_code=http_status, detail={"code": code, "message": message})


def _authentication_required() -> AuthenticationError:
    return AuthenticationError(
        "authentication_required", status.HTTP_401_UNAUTHORIZED, "Authentication is required"
    )


def _authentication_invalid() -> AuthenticationError:
    return AuthenticationError(
        "authentication_invalid",
        status.HTTP_401_UNAUTHORIZED,
        "Authentication credentials are invalid",
    )


def _authentication_unavailable() -> AuthenticationError:
    return AuthenticationError(
        "authentication_unavailable",
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "Authentication is not available",
    )


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise _authentication_required()
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise _authentication_required()
    token = parts[1].strip()
    if not token:
        raise _authentication_required()
    return token


@lru_cache(maxsize=8)
def _jwks_client(jwks_url: str) -> PyJWKClient:
    """One reusable PyJWKClient per configured JWKS URL: cached keys,
    kid-based lookup, refetch-on-unknown-kid -- never constructed per request."""
    return PyJWKClient(jwks_url, cache_keys=True)


def _derive_user_id(issuer: str, subject: str) -> UUID:
    """Deterministic identity derivation: uuid5(namespace, canonical).

    canonical = "<len(issuer)>:<issuer>:<subject>"

    The issuer is length-prefixed so the join is unambiguous even though
    both issuer (a URL, typically containing ':') and subject (an opaque,
    provider-defined string) may themselves contain ':'. Without the length
    prefix, issuer="a:b"+subject="c" and issuer="a"+subject="b:c" would
    collide on the naive join "a:b:c". Neither issuer nor subject is
    normalized (no case-folding, no trimming beyond what the verified JWT
    claim already contains) -- they are used exactly as verified.

    This algorithm must never change: changing it re-derives a different
    user_id for every existing identity and breaks membership continuity.
    """
    canonical = f"{len(issuer)}:{issuer}:{subject}"
    return uuid5(GOVERNED_INTEL4OPS_IDENTITY_NAMESPACE, canonical)


class OIDCIdentityProvider:
    """Provider-neutral OIDC/JWT resource-server verifier. Intel4Ops never
    issues tokens, never handles credentials, and never performs any OAuth
    flow -- it only verifies bearer tokens issued by a deployment-configured,
    standards-compliant OIDC provider."""

    def authenticate(self, authorization: str | None) -> AuthenticatedUser:
        settings = get_settings()
        if not (settings.oidc_issuer and settings.oidc_audience and settings.oidc_jwks_url):
            raise _authentication_unavailable()
        algorithms = settings.oidc_allowed_algorithm_list
        if not algorithms:
            raise _authentication_unavailable()

        token = _extract_bearer_token(authorization)

        try:
            jwks_client = _jwks_client(settings.oidc_jwks_url)
            signing_key = jwks_client.get_signing_key_from_jwt(token)
        except PyJWKClientConnectionError as exc:
            raise _authentication_unavailable() from exc
        except (PyJWKClientError, PyJWTError) as exc:
            raise _authentication_invalid() from exc

        try:
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=algorithms,
                issuer=settings.oidc_issuer,
                audience=settings.oidc_audience,
                options={"require": ["exp", "iss", "aud", "sub"]},
            )
        except PyJWTError as exc:
            raise _authentication_invalid() from exc

        issuer = payload.get("iss")
        subject = payload.get("sub")
        if not isinstance(issuer, str) or not issuer or not isinstance(subject, str) or not subject:
            raise _authentication_invalid()

        # Namespaced under the configured API audience -- Auth0 (and OIDC
        # generally) rejects non-namespaced custom claims on access tokens,
        # so these are only ever read under "<audience>/email" and
        # "<audience>/email_verified", exactly as provisioned by the
        # deployment's Post-Login Action. Never a bare "email"/
        # "email_verified" claim: those are ID-token-only under standard
        # OIDC and are not present on the access token Core validates here.
        email_claim = payload.get(f"{settings.oidc_audience}/email")
        email = email_claim if isinstance(email_claim, str) and email_claim else None
        email_verified = payload.get(f"{settings.oidc_audience}/email_verified") is True

        # is_platform_admin is unconditionally False for every OIDC customer
        # identity in this remediation. No claim is read for it. Platform-
        # admin authentication is deferred to a future, explicitly-governed
        # package.
        return AuthenticatedUser(
            user_id=_derive_user_id(issuer, subject),
            is_platform_admin=False,
            email=email,
            email_verified=email_verified,
        )


_identity_provider: IdentityProvider = OIDCIdentityProvider()


def get_current_user(authorization: str | None = Header(default=None)) -> AuthenticatedUser:
    return _identity_provider.authenticate(authorization)
