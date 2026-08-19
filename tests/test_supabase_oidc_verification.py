"""P3.xxA.3B -- confirms the existing, provider-neutral OIDCIdentityProvider
verifies ES256/JWKS-signed tokens shaped like IntelOps Navigator's Supabase
Auth tokens, with zero code changes: only OIDC_ALLOWED_ALGORITHMS needs to
name ES256. All JWKS lookups here are monkeypatched (PyJWKClient.fetch_data)
-- nothing in this file makes a live network call to Supabase or anywhere
else.

Confirmed Navigator/Supabase contract (see docs/architecture/supabase-navigator-oidc.md):
  OIDC_ISSUER=https://ewdogwyowzqbjfyhkpxt.supabase.co/auth/v1
  OIDC_AUDIENCE=authenticated
  OIDC_JWKS_URL=https://ewdogwyowzqbjfyhkpxt.supabase.co/auth/v1/.well-known/jwks.json
  OIDC_ALLOWED_ALGORITHMS=ES256
"""

import time
from typing import Any
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePrivateKey
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from jwt import PyJWKClient
from jwt.algorithms import ECAlgorithm

import app.auth.identity as identity_module
from app.auth.identity import (
    AuthenticatedUser,
    AuthenticationError,
    OIDCIdentityProvider,
    _derive_user_id,
    get_current_user,
)
from app.core.config import Settings

ISSUER = "https://ewdogwyowzqbjfyhkpxt.supabase.co/auth/v1"
AUDIENCE = "authenticated"
JWKS_URL_BASE = "https://ewdogwyowzqbjfyhkpxt.supabase.co/auth/v1/.well-known/jwks.json"
SUPABASE_SUBJECT = "3fa85f64-5717-4562-b3fc-2c963f66afa6"  # a stable Supabase user UUID


def _unique_jwks_url() -> str:
    return f"{JWKS_URL_BASE}?probe={uuid4().hex}"


def _new_ec_key() -> EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


def _jwk_for(key: EllipticCurvePrivateKey, kid: str) -> dict[str, Any]:
    jwk = ECAlgorithm.to_jwk(key.public_key(), as_dict=True)
    jwk.update({"kid": kid, "use": "sig", "alg": "ES256"})
    return jwk


def _jwks_document(*keys: tuple[EllipticCurvePrivateKey, str]) -> dict[str, Any]:
    return {"keys": [_jwk_for(key, kid) for key, kid in keys]}


def _sign(
    key: EllipticCurvePrivateKey,
    kid: str,
    *,
    issuer: str = ISSUER,
    audience: str = AUDIENCE,
    subject: str = SUPABASE_SUBJECT,
    algorithm: str = "ES256",
    expires_in: int = 3600,
) -> str:
    now = int(time.time())
    payload = {
        "iss": issuer,
        "aud": audience,
        "sub": subject,
        "iat": now,
        "exp": now + expires_in,
        # Supabase's real access tokens carry these too; harmless noise the
        # provider is expected to ignore (it only reads iss/sub/aud/exp/nbf
        # plus the namespaced email claims it doesn't find here).
        "role": "authenticated",
        "aal": "aal1",
    }
    return jwt.encode(payload, key, algorithm=algorithm, headers={"kid": kid})


def _configure(monkeypatch: pytest.MonkeyPatch, *, algorithms: str = "ES256") -> Settings:
    settings = Settings(
        oidc_issuer=ISSUER,
        oidc_audience=AUDIENCE,
        oidc_jwks_url=_unique_jwks_url(),
        oidc_allowed_algorithms=algorithms,
    )
    monkeypatch.setattr(identity_module, "get_settings", lambda: settings)
    return settings


def _patch_jwks_fetch(monkeypatch: pytest.MonkeyPatch, document: dict[str, Any]) -> None:
    monkeypatch.setattr(PyJWKClient, "fetch_data", lambda self: document)


@pytest.fixture
def provider() -> OIDCIdentityProvider:
    return OIDCIdentityProvider()


# ---------------------------------------------------------------------------
# 1. Valid Supabase-style ES256 JWT -> AuthenticatedUser
# ---------------------------------------------------------------------------


def test_valid_es256_supabase_jwt_authenticates(
    monkeypatch: pytest.MonkeyPatch, provider: OIDCIdentityProvider
) -> None:
    key = _new_ec_key()
    _configure(monkeypatch)
    _patch_jwks_fetch(monkeypatch, _jwks_document((key, "supabase-kid-1")))
    token = _sign(key, "supabase-kid-1")

    user = provider.authenticate(f"Bearer {token}")

    assert isinstance(user, AuthenticatedUser)
    assert user.is_platform_admin is False
    assert user.user_id == _derive_user_id(ISSUER, SUPABASE_SUBJECT)


# ---------------------------------------------------------------------------
# 2. sub -> stable Intel4Ops user_id
# ---------------------------------------------------------------------------


def test_supabase_sub_claim_produces_stable_user_id(
    monkeypatch: pytest.MonkeyPatch, provider: OIDCIdentityProvider
) -> None:
    key = _new_ec_key()
    _configure(monkeypatch)
    _patch_jwks_fetch(monkeypatch, _jwks_document((key, "supabase-kid-1")))

    first = provider.authenticate(f"Bearer {_sign(key, 'supabase-kid-1')}")
    second = provider.authenticate(f"Bearer {_sign(key, 'supabase-kid-1')}")

    assert first.user_id == second.user_id == _derive_user_id(ISSUER, SUPABASE_SUBJECT)


# ---------------------------------------------------------------------------
# 3. Wrong issuer rejected
# ---------------------------------------------------------------------------


def test_wrong_issuer_rejected(
    monkeypatch: pytest.MonkeyPatch, provider: OIDCIdentityProvider
) -> None:
    key = _new_ec_key()
    _configure(monkeypatch)
    _patch_jwks_fetch(monkeypatch, _jwks_document((key, "supabase-kid-1")))
    token = _sign(key, "supabase-kid-1", issuer="https://attacker-project.supabase.co/auth/v1")

    with pytest.raises(AuthenticationError) as excinfo:
        provider.authenticate(f"Bearer {token}")
    assert excinfo.value.detail["code"] == "authentication_invalid"


# ---------------------------------------------------------------------------
# 4. Wrong audience rejected
# ---------------------------------------------------------------------------


def test_wrong_audience_rejected(
    monkeypatch: pytest.MonkeyPatch, provider: OIDCIdentityProvider
) -> None:
    key = _new_ec_key()
    _configure(monkeypatch)
    _patch_jwks_fetch(monkeypatch, _jwks_document((key, "supabase-kid-1")))
    # "anon" is Supabase's other standard audience value (unauthenticated
    # client role) -- must not be accepted where "authenticated" is required.
    token = _sign(key, "supabase-kid-1", audience="anon")

    with pytest.raises(AuthenticationError) as excinfo:
        provider.authenticate(f"Bearer {token}")
    assert excinfo.value.detail["code"] == "authentication_invalid"


# ---------------------------------------------------------------------------
# 5. Expired token rejected
# ---------------------------------------------------------------------------


def test_expired_token_rejected(
    monkeypatch: pytest.MonkeyPatch, provider: OIDCIdentityProvider
) -> None:
    key = _new_ec_key()
    _configure(monkeypatch)
    _patch_jwks_fetch(monkeypatch, _jwks_document((key, "supabase-kid-1")))
    token = _sign(key, "supabase-kid-1", expires_in=-60)

    with pytest.raises(AuthenticationError) as excinfo:
        provider.authenticate(f"Bearer {token}")
    assert excinfo.value.detail["code"] == "authentication_invalid"


# ---------------------------------------------------------------------------
# 6. Invalid signature rejected
# ---------------------------------------------------------------------------


def test_tampered_signature_rejected(
    monkeypatch: pytest.MonkeyPatch, provider: OIDCIdentityProvider
) -> None:
    key = _new_ec_key()
    _configure(monkeypatch)
    _patch_jwks_fetch(monkeypatch, _jwks_document((key, "supabase-kid-1")))
    token = _sign(key, "supabase-kid-1")
    header, payload, signature = token.split(".")
    tampered = f"{header}.{payload}.{signature[:-2]}{'AA' if signature[-2:] != 'AA' else 'BB'}"

    with pytest.raises(AuthenticationError) as excinfo:
        provider.authenticate(f"Bearer {tampered}")
    assert excinfo.value.detail["code"] == "authentication_invalid"


def test_wrong_signing_key_rejected(
    monkeypatch: pytest.MonkeyPatch, provider: OIDCIdentityProvider
) -> None:
    trusted_key = _new_ec_key()
    attacker_key = _new_ec_key()
    _configure(monkeypatch)
    # JWKS only publishes the trusted key under this kid; an attacker signs
    # with a different EC key but claims the same kid.
    _patch_jwks_fetch(monkeypatch, _jwks_document((trusted_key, "supabase-kid-1")))
    token = _sign(attacker_key, "supabase-kid-1")

    with pytest.raises(AuthenticationError) as excinfo:
        provider.authenticate(f"Bearer {token}")
    assert excinfo.value.detail["code"] == "authentication_invalid"


# ---------------------------------------------------------------------------
# Algorithm allowlist is still enforced for ES256 the same way it is for
# RS256 -- a deployment left at the RS256-only default must not silently
# accept a Supabase ES256 token, and vice versa.
# ---------------------------------------------------------------------------


def test_es256_token_rejected_when_allowlist_is_rs256_only(
    monkeypatch: pytest.MonkeyPatch, provider: OIDCIdentityProvider
) -> None:
    key = _new_ec_key()
    _configure(monkeypatch, algorithms="RS256")
    _patch_jwks_fetch(monkeypatch, _jwks_document((key, "supabase-kid-1")))
    token = _sign(key, "supabase-kid-1")

    with pytest.raises(AuthenticationError) as excinfo:
        provider.authenticate(f"Bearer {token}")
    assert excinfo.value.detail["code"] == "authentication_invalid"


# ---------------------------------------------------------------------------
# 7. GET /api/v1/me works end-to-end with a valid Supabase-style token
# ---------------------------------------------------------------------------


def test_live_me_endpoint_accepts_valid_es256_supabase_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from collections.abc import Generator as _Generator

    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.db.session import Base, get_db
    from app.main import app

    key = _new_ec_key()
    _configure(monkeypatch)
    _patch_jwks_fetch(monkeypatch, _jwks_document((key, "supabase-kid-1")))
    token = _sign(key, "supabase-kid-1")

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection: object, _: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_get_db() -> _Generator[Any, None, None]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    finally:
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(engine)
        engine.dispose()

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == str(_derive_user_id(ISSUER, SUPABASE_SUBJECT))
    assert body["is_platform_admin"] is False
    assert body["memberships"] == []


# ---------------------------------------------------------------------------
# 9. Pilot bridge stays intact as a fallback alongside real Supabase OIDC --
# a pilot bearer token still resolves to the pilot identity even when OIDC
# is fully configured for Supabase, and a real Supabase token still falls
# through past the (inapplicable) pilot checks to OIDC verification.
# ---------------------------------------------------------------------------


def test_pilot_bridge_still_resolves_alongside_configured_supabase_oidc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pilot_user_id = uuid4()
    settings = Settings(
        app_env="pilot",
        oidc_issuer=ISSUER,
        oidc_audience=AUDIENCE,
        oidc_jwks_url=_unique_jwks_url(),
        oidc_allowed_algorithms="ES256",
        pilot_auth_enabled=True,
        pilot_auth_token="pilot-fallback-secret",  # noqa: S105 -- test fixture
        pilot_user_id=pilot_user_id,
        pilot_platform_admin=True,
    )
    monkeypatch.setattr(identity_module, "get_settings", lambda: settings)

    probe_app = FastAPI()

    @probe_app.get("/probe")
    def probe(user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, object]:
        return {"user_id": str(user.user_id), "is_platform_admin": user.is_platform_admin}

    client = TestClient(probe_app)

    response = client.get("/probe", headers={"Authorization": "Bearer pilot-fallback-secret"})

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == str(pilot_user_id)
    assert body["is_platform_admin"] is True


def test_real_supabase_token_falls_through_pilot_checks_to_oidc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = _new_ec_key()
    settings = Settings(
        app_env="pilot",
        oidc_issuer=ISSUER,
        oidc_audience=AUDIENCE,
        oidc_jwks_url=_unique_jwks_url(),
        oidc_allowed_algorithms="ES256",
        pilot_auth_enabled=True,
        pilot_auth_token="pilot-fallback-secret",  # noqa: S105 -- test fixture
        pilot_user_id=uuid4(),
        pilot_platform_admin=True,
    )
    monkeypatch.setattr(identity_module, "get_settings", lambda: settings)
    _patch_jwks_fetch(monkeypatch, _jwks_document((key, "supabase-kid-1")))
    token = _sign(key, "supabase-kid-1")

    probe_app = FastAPI()

    @probe_app.get("/probe")
    def probe(user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, object]:
        return {"user_id": str(user.user_id), "is_platform_admin": user.is_platform_admin}

    client = TestClient(probe_app)

    response = client.get("/probe", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == str(_derive_user_id(ISSUER, SUPABASE_SUBJECT))
    assert body["is_platform_admin"] is False
