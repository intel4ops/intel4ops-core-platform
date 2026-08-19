import base64
import hashlib
import hmac
import json
import time
from typing import Any
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePrivateKey
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from jwt import PyJWKClient
from jwt.algorithms import ECAlgorithm, RSAAlgorithm

import app.auth.identity as identity_module
from app.auth.identity import (
    AuthenticationError,
    OIDCIdentityProvider,
    _derive_user_id,
    get_current_user,
)
from app.core.config import Settings

ISSUER = "https://issuer.test/"
AUDIENCE = "intel4ops-test-audience"

# Shape of the live SBASE-01 Supabase contract: a project-specific issuer
# URL, the fixed "authenticated" role literal as audience, ES256 signing.
SUPABASE_ISSUER = "https://valgxugrfkoaqlttigph.supabase.co/auth/v1"
SUPABASE_AUDIENCE = "authenticated"


def _unique_jwks_url() -> str:
    return f"https://idp.test/jwks/{uuid4().hex}.json"


def _new_rsa_key() -> RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _new_ec_key() -> EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


def _jwk_for(key: RSAPrivateKey | EllipticCurvePrivateKey, kid: str) -> dict[str, Any]:
    if isinstance(key, RSAPrivateKey):
        jwk = RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
        jwk.update({"kid": kid, "use": "sig", "alg": "RS256"})
    else:
        jwk = ECAlgorithm.to_jwk(key.public_key(), as_dict=True)
        jwk.update({"kid": kid, "use": "sig", "alg": "ES256"})
    return jwk


def _jwks_document(*keys: tuple[RSAPrivateKey | EllipticCurvePrivateKey, str]) -> dict[str, Any]:
    return {"keys": [_jwk_for(key, kid) for key, kid in keys]}


def _sign(
    key: RSAPrivateKey | EllipticCurvePrivateKey,
    kid: str,
    *,
    issuer: str = ISSUER,
    audience: str = AUDIENCE,
    subject: str = "user-123",
    algorithm: str = "RS256",
    expires_in: int = 3600,
    not_before_offset: int | None = None,
    extra_claims: dict[str, Any] | None = None,
    omit_claims: tuple[str, ...] = (),
) -> str:
    now = int(time.time())
    payload: dict[str, Any] = {
        "iss": issuer,
        "aud": audience,
        "sub": subject,
        "iat": now,
        "exp": now + expires_in,
    }
    if not_before_offset is not None:
        payload["nbf"] = now + not_before_offset
    if extra_claims:
        payload.update(extra_claims)
    for claim in omit_claims:
        payload.pop(claim, None)
    return jwt.encode(payload, key, algorithm=algorithm, headers={"kid": kid})


def _configure(
    monkeypatch: pytest.MonkeyPatch,
    *,
    issuer: str | None = ISSUER,
    audience: str | None = AUDIENCE,
    jwks_url: str | None,
    algorithms: str = "RS256",
) -> None:
    settings = Settings(
        oidc_issuer=issuer,
        oidc_audience=audience,
        oidc_jwks_url=jwks_url,
        oidc_allowed_algorithms=algorithms,
    )
    monkeypatch.setattr(identity_module, "get_settings", lambda: settings)


def _patch_jwks_fetch(monkeypatch: pytest.MonkeyPatch, document: dict[str, Any]) -> None:
    monkeypatch.setattr(PyJWKClient, "fetch_data", lambda self: document)


def _patch_jwks_fetch_sequence(
    monkeypatch: pytest.MonkeyPatch, documents: list[dict[str, Any]]
) -> None:
    calls = {"count": 0}

    def fetch(self: PyJWKClient) -> dict[str, Any]:
        index = min(calls["count"], len(documents) - 1)
        calls["count"] += 1
        return documents[index]

    monkeypatch.setattr(PyJWKClient, "fetch_data", fetch)


@pytest.fixture
def provider() -> OIDCIdentityProvider:
    return OIDCIdentityProvider()


# ---------------------------------------------------------------------------
# 1. valid RS256 signed JWT authenticates
# ---------------------------------------------------------------------------
def test_valid_rs256_jwt_authenticates(
    monkeypatch: pytest.MonkeyPatch, provider: OIDCIdentityProvider
) -> None:
    key = _new_rsa_key()
    url = _unique_jwks_url()
    _configure(monkeypatch, jwks_url=url)
    _patch_jwks_fetch(monkeypatch, _jwks_document((key, "kid-1")))
    token = _sign(key, "kid-1")

    user = provider.authenticate(f"Bearer {token}")

    assert user.is_platform_admin is False
    assert user.user_id == _derive_user_id(ISSUER, "user-123")
    assert user.email is None
    assert user.email_verified is False


# ---------------------------------------------------------------------------
# 1b. SBASE-03: email/email_verified are read from the standard top-level
# "email"/"email_verified" claims (Supabase's actual shape), never from the
# CMVP-01 Auth0 namespaced "<audience>/email" pattern, and never from
# nested user_metadata -- Supabase's own client-editable, untrusted field.
# ---------------------------------------------------------------------------
def test_top_level_email_claims_extracted(
    monkeypatch: pytest.MonkeyPatch, provider: OIDCIdentityProvider
) -> None:
    key = _new_rsa_key()
    url = _unique_jwks_url()
    _configure(monkeypatch, jwks_url=url)
    _patch_jwks_fetch(monkeypatch, _jwks_document((key, "kid-1")))
    token = _sign(
        key,
        "kid-1",
        extra_claims={"email": "Pilot.User@Example.com", "email_verified": True},
    )

    user = provider.authenticate(f"Bearer {token}")

    assert user.email == "Pilot.User@Example.com"
    assert user.email_verified is True


def test_namespaced_email_claim_no_longer_read(
    monkeypatch: pytest.MonkeyPatch, provider: OIDCIdentityProvider
) -> None:
    """Regression guard: the retired Auth0 namespaced-claim pattern must not
    be silently reintroduced or accidentally still matched."""
    key = _new_rsa_key()
    url = _unique_jwks_url()
    _configure(monkeypatch, jwks_url=url)
    _patch_jwks_fetch(monkeypatch, _jwks_document((key, "kid-1")))
    token = _sign(
        key,
        "kid-1",
        extra_claims={
            f"{AUDIENCE}/email": "namespaced@example.com",
            f"{AUDIENCE}/email_verified": True,
        },
    )

    user = provider.authenticate(f"Bearer {token}")

    assert user.email is None
    assert user.email_verified is False


def test_user_metadata_email_verified_never_trusted(
    monkeypatch: pytest.MonkeyPatch, provider: OIDCIdentityProvider
) -> None:
    """SBASE-01 finding: Supabase's access token carries no trustworthy
    top-level email_verified claim, only the client-editable
    user_metadata.email_verified. That field must never be read as
    authorization-relevant evidence, no matter how it's nested -- doing so
    would let an authenticated user assert their own verification status."""
    key = _new_rsa_key()
    url = _unique_jwks_url()
    _configure(monkeypatch, jwks_url=url)
    _patch_jwks_fetch(monkeypatch, _jwks_document((key, "kid-1")))
    token = _sign(
        key,
        "kid-1",
        extra_claims={
            "email": "pilot@example.com",
            "user_metadata": {"email": "pilot@example.com", "email_verified": True},
        },
    )

    user = provider.authenticate(f"Bearer {token}")

    assert user.email == "pilot@example.com"
    assert user.email_verified is False


def test_email_verified_string_true_not_treated_as_verified(
    monkeypatch: pytest.MonkeyPatch, provider: OIDCIdentityProvider
) -> None:
    """Only the JSON boolean `true` counts -- a truthy-looking string must
    not be accepted, since `bool("false")` is True in Python."""
    key = _new_rsa_key()
    url = _unique_jwks_url()
    _configure(monkeypatch, jwks_url=url)
    _patch_jwks_fetch(monkeypatch, _jwks_document((key, "kid-1")))
    token = _sign(
        key,
        "kid-1",
        extra_claims={"email": "pilot@example.com", "email_verified": "false"},
    )

    user = provider.authenticate(f"Bearer {token}")

    assert user.email == "pilot@example.com"
    assert user.email_verified is False


# ---------------------------------------------------------------------------
# 2. derived UUID is deterministic
# ---------------------------------------------------------------------------
def test_derived_uuid_is_deterministic(
    monkeypatch: pytest.MonkeyPatch, provider: OIDCIdentityProvider
) -> None:
    key = _new_rsa_key()
    url = _unique_jwks_url()
    _configure(monkeypatch, jwks_url=url)
    _patch_jwks_fetch(monkeypatch, _jwks_document((key, "kid-1")))

    first = provider.authenticate(f"Bearer {_sign(key, 'kid-1')}")
    second = provider.authenticate(f"Bearer {_sign(key, 'kid-1')}")

    assert first.user_id == second.user_id


# ---------------------------------------------------------------------------
# 3. same subject + different issuer produces different UUID
# ---------------------------------------------------------------------------
def test_same_subject_different_issuer_yields_different_uuid() -> None:
    a = _derive_user_id("https://issuer-a.test/", "user-123")
    b = _derive_user_id("https://issuer-b.test/", "user-123")
    assert a != b


def test_derivation_join_is_unambiguous_across_boundary() -> None:
    # issuer "a:b" + subject "c"  vs  issuer "a" + subject "b:c"
    # must not collide despite naive concatenation producing "a:b:c" either way.
    left = _derive_user_id("a:b", "c")
    right = _derive_user_id("a", "b:c")
    assert left != right


# ---------------------------------------------------------------------------
# 4. missing Authorization header rejected
# ---------------------------------------------------------------------------
def test_missing_authorization_header_rejected(
    monkeypatch: pytest.MonkeyPatch, provider: OIDCIdentityProvider
) -> None:
    _configure(monkeypatch, jwks_url=_unique_jwks_url())
    with pytest.raises(AuthenticationError) as excinfo:
        provider.authenticate(None)
    assert excinfo.value.detail["code"] == "authentication_required"
    assert excinfo.value.status_code == 401


# ---------------------------------------------------------------------------
# 5. malformed Bearer header rejected
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "header",
    ["", "Bearer", "Bearer ", "Basic abcdef", "Token abc", "BearerXabc"],
)
def test_malformed_authorization_header_rejected(
    monkeypatch: pytest.MonkeyPatch, provider: OIDCIdentityProvider, header: str
) -> None:
    _configure(monkeypatch, jwks_url=_unique_jwks_url())
    with pytest.raises(AuthenticationError) as excinfo:
        provider.authenticate(header)
    assert excinfo.value.detail["code"] == "authentication_required"


# ---------------------------------------------------------------------------
# 6. tampered signature rejected
# ---------------------------------------------------------------------------
def test_tampered_signature_rejected(
    monkeypatch: pytest.MonkeyPatch, provider: OIDCIdentityProvider
) -> None:
    key = _new_rsa_key()
    url = _unique_jwks_url()
    _configure(monkeypatch, jwks_url=url)
    _patch_jwks_fetch(monkeypatch, _jwks_document((key, "kid-1")))
    token = _sign(key, "kid-1")
    header, payload, signature = token.split(".")
    tampered = f"{header}.{payload}.{signature[:-2]}{'AA' if signature[-2:] != 'AA' else 'BB'}"

    with pytest.raises(AuthenticationError) as excinfo:
        provider.authenticate(f"Bearer {tampered}")
    assert excinfo.value.detail["code"] == "authentication_invalid"


# ---------------------------------------------------------------------------
# 7. expired JWT rejected
# ---------------------------------------------------------------------------
def test_expired_jwt_rejected(
    monkeypatch: pytest.MonkeyPatch, provider: OIDCIdentityProvider
) -> None:
    key = _new_rsa_key()
    url = _unique_jwks_url()
    _configure(monkeypatch, jwks_url=url)
    _patch_jwks_fetch(monkeypatch, _jwks_document((key, "kid-1")))
    token = _sign(key, "kid-1", expires_in=-60)

    with pytest.raises(AuthenticationError) as excinfo:
        provider.authenticate(f"Bearer {token}")
    assert excinfo.value.detail["code"] == "authentication_invalid"


# ---------------------------------------------------------------------------
# 8. not-before JWT rejected
# ---------------------------------------------------------------------------
def test_not_before_jwt_rejected(
    monkeypatch: pytest.MonkeyPatch, provider: OIDCIdentityProvider
) -> None:
    key = _new_rsa_key()
    url = _unique_jwks_url()
    _configure(monkeypatch, jwks_url=url)
    _patch_jwks_fetch(monkeypatch, _jwks_document((key, "kid-1")))
    token = _sign(key, "kid-1", not_before_offset=3600)

    with pytest.raises(AuthenticationError) as excinfo:
        provider.authenticate(f"Bearer {token}")
    assert excinfo.value.detail["code"] == "authentication_invalid"


# ---------------------------------------------------------------------------
# 9. wrong issuer rejected
# ---------------------------------------------------------------------------
def test_wrong_issuer_rejected(
    monkeypatch: pytest.MonkeyPatch, provider: OIDCIdentityProvider
) -> None:
    key = _new_rsa_key()
    url = _unique_jwks_url()
    _configure(monkeypatch, jwks_url=url)
    _patch_jwks_fetch(monkeypatch, _jwks_document((key, "kid-1")))
    token = _sign(key, "kid-1", issuer="https://attacker.test/")

    with pytest.raises(AuthenticationError) as excinfo:
        provider.authenticate(f"Bearer {token}")
    assert excinfo.value.detail["code"] == "authentication_invalid"


# ---------------------------------------------------------------------------
# 10. wrong audience rejected
# ---------------------------------------------------------------------------
def test_wrong_audience_rejected(
    monkeypatch: pytest.MonkeyPatch, provider: OIDCIdentityProvider
) -> None:
    key = _new_rsa_key()
    url = _unique_jwks_url()
    _configure(monkeypatch, jwks_url=url)
    _patch_jwks_fetch(monkeypatch, _jwks_document((key, "kid-1")))
    token = _sign(key, "kid-1", audience="someone-elses-audience")

    with pytest.raises(AuthenticationError) as excinfo:
        provider.authenticate(f"Bearer {token}")
    assert excinfo.value.detail["code"] == "authentication_invalid"


# ---------------------------------------------------------------------------
# 11. wrong signing key rejected
# ---------------------------------------------------------------------------
def test_wrong_signing_key_rejected(
    monkeypatch: pytest.MonkeyPatch, provider: OIDCIdentityProvider
) -> None:
    trusted_key = _new_rsa_key()
    attacker_key = _new_rsa_key()
    url = _unique_jwks_url()
    _configure(monkeypatch, jwks_url=url)
    # JWKS only publishes the trusted key under kid-1; attacker signs with a
    # different key but claims the same kid so the lookup still resolves,
    # and the signature check must be what rejects it.
    _patch_jwks_fetch(monkeypatch, _jwks_document((trusted_key, "kid-1")))
    token = _sign(attacker_key, "kid-1")

    with pytest.raises(AuthenticationError) as excinfo:
        provider.authenticate(f"Bearer {token}")
    assert excinfo.value.detail["code"] == "authentication_invalid"


# ---------------------------------------------------------------------------
# 12. unknown kid rejected
# ---------------------------------------------------------------------------
def test_unknown_kid_rejected(
    monkeypatch: pytest.MonkeyPatch, provider: OIDCIdentityProvider
) -> None:
    key = _new_rsa_key()
    url = _unique_jwks_url()
    _configure(monkeypatch, jwks_url=url)
    _patch_jwks_fetch(monkeypatch, _jwks_document((key, "kid-1")))
    token = _sign(key, "kid-does-not-exist")

    with pytest.raises(AuthenticationError) as excinfo:
        provider.authenticate(f"Bearer {token}")
    assert excinfo.value.detail["code"] == "authentication_invalid"


# ---------------------------------------------------------------------------
# 13. missing subject rejected
# ---------------------------------------------------------------------------
def test_missing_subject_rejected(
    monkeypatch: pytest.MonkeyPatch, provider: OIDCIdentityProvider
) -> None:
    key = _new_rsa_key()
    url = _unique_jwks_url()
    _configure(monkeypatch, jwks_url=url)
    _patch_jwks_fetch(monkeypatch, _jwks_document((key, "kid-1")))
    token = _sign(key, "kid-1", omit_claims=("sub",))

    with pytest.raises(AuthenticationError) as excinfo:
        provider.authenticate(f"Bearer {token}")
    assert excinfo.value.detail["code"] == "authentication_invalid"


# ---------------------------------------------------------------------------
# 14. empty subject rejected
# ---------------------------------------------------------------------------
def test_empty_subject_rejected(
    monkeypatch: pytest.MonkeyPatch, provider: OIDCIdentityProvider
) -> None:
    key = _new_rsa_key()
    url = _unique_jwks_url()
    _configure(monkeypatch, jwks_url=url)
    _patch_jwks_fetch(monkeypatch, _jwks_document((key, "kid-1")))
    token = _sign(key, "kid-1", subject="")

    with pytest.raises(AuthenticationError) as excinfo:
        provider.authenticate(f"Bearer {token}")
    assert excinfo.value.detail["code"] == "authentication_invalid"


# ---------------------------------------------------------------------------
# 15. unsupported algorithm rejected
# ---------------------------------------------------------------------------
def test_unsupported_algorithm_rejected(
    monkeypatch: pytest.MonkeyPatch, provider: OIDCIdentityProvider
) -> None:
    key = _new_rsa_key()
    url = _unique_jwks_url()
    _configure(monkeypatch, jwks_url=url, algorithms="RS256")
    _patch_jwks_fetch(monkeypatch, _jwks_document((key, "kid-1")))
    # PS256 is a legitimate, secure asymmetric algorithm -- but it's not the
    # one this deployment allows, so it must still be rejected.
    token = _sign(key, "kid-1", algorithm="PS256")

    with pytest.raises(AuthenticationError) as excinfo:
        provider.authenticate(f"Bearer {token}")
    assert excinfo.value.detail["code"] == "authentication_invalid"


# ---------------------------------------------------------------------------
# 16. algorithm-confusion attempt rejected
# ---------------------------------------------------------------------------
def test_algorithm_confusion_attempt_rejected(
    monkeypatch: pytest.MonkeyPatch, provider: OIDCIdentityProvider
) -> None:
    key = _new_rsa_key()
    url = _unique_jwks_url()
    _configure(monkeypatch, jwks_url=url, algorithms="RS256")
    _patch_jwks_fetch(monkeypatch, _jwks_document((key, "kid-1")))
    public_pem = key.public_key().public_bytes(
        encoding=Encoding.PEM,
        format=PublicFormat.SubjectPublicKeyInfo,
    )

    # Classic RS256->HS256 confusion: sign with HS256 using the RSA public
    # key bytes as the "shared secret". PyJWT's own encode() refuses to
    # build this (it detects a PEM key passed as an HMAC secret), which is
    # exactly the client-side guard a real attacker's tooling would not
    # have -- so the token is hand-built here to reach our decode path with
    # the forged signature, which must be rejected purely because HS256 is
    # not in the allowed-algorithms list, never reached as a candidate key
    # type.
    def _b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    header = _b64url(json.dumps({"alg": "HS256", "kid": "kid-1"}).encode())
    payload = _b64url(
        json.dumps(
            {"iss": ISSUER, "aud": AUDIENCE, "sub": "user-123", "exp": int(time.time()) + 3600}
        ).encode()
    )
    signing_input = f"{header}.{payload}".encode()
    signature = _b64url(hmac.new(public_pem, signing_input, hashlib.sha256).digest())
    forged = f"{header}.{payload}.{signature}"

    with pytest.raises(AuthenticationError) as excinfo:
        provider.authenticate(f"Bearer {forged}")
    assert excinfo.value.detail["code"] == "authentication_invalid"


# ---------------------------------------------------------------------------
# 17. unsigned token rejected
# ---------------------------------------------------------------------------
def test_unsigned_token_rejected(
    monkeypatch: pytest.MonkeyPatch, provider: OIDCIdentityProvider
) -> None:
    key = _new_rsa_key()
    url = _unique_jwks_url()
    _configure(monkeypatch, jwks_url=url, algorithms="RS256")
    _patch_jwks_fetch(monkeypatch, _jwks_document((key, "kid-1")))
    unsigned = jwt.encode(
        {"iss": ISSUER, "aud": AUDIENCE, "sub": "user-123", "exp": int(time.time()) + 3600},
        key="",
        algorithm="none",
        headers={"kid": "kid-1"},
    )

    with pytest.raises(AuthenticationError) as excinfo:
        provider.authenticate(f"Bearer {unsigned}")
    assert excinfo.value.detail["code"] == "authentication_invalid"


# ---------------------------------------------------------------------------
# 18 & 19. valid token cannot set platform_admin / forged claim stays false
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "extra_claims",
    [
        {"is_platform_admin": True},
        {"platform_admin": True},
        {"role": "platform_admin"},
        {"roles": ["platform_admin"]},
        {"is_platform_admin": "true"},
    ],
)
def test_forged_platform_admin_claim_ignored(
    monkeypatch: pytest.MonkeyPatch,
    provider: OIDCIdentityProvider,
    extra_claims: dict[str, Any],
) -> None:
    key = _new_rsa_key()
    url = _unique_jwks_url()
    _configure(monkeypatch, jwks_url=url)
    _patch_jwks_fetch(monkeypatch, _jwks_document((key, "kid-1")))
    token = _sign(key, "kid-1", extra_claims=extra_claims)

    user = provider.authenticate(f"Bearer {token}")

    assert user.is_platform_admin is False


# ---------------------------------------------------------------------------
# 20. missing OIDC configuration fails closed
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "kwargs",
    [
        {"issuer": None},
        {"audience": None},
        {"jwks_url": None},
        {"algorithms": ""},
    ],
)
def test_missing_oidc_configuration_fails_closed(
    monkeypatch: pytest.MonkeyPatch, provider: OIDCIdentityProvider, kwargs: dict[str, Any]
) -> None:
    base = {"issuer": ISSUER, "audience": AUDIENCE, "jwks_url": _unique_jwks_url()}
    base.update(kwargs)
    _configure(monkeypatch, **base)

    with pytest.raises(AuthenticationError) as excinfo:
        provider.authenticate("Bearer irrelevant-token")
    assert excinfo.value.detail["code"] == "authentication_unavailable"
    assert excinfo.value.status_code == 503


# ---------------------------------------------------------------------------
# 21. JWKS fetch failure fails closed
# ---------------------------------------------------------------------------
def test_jwks_fetch_failure_fails_closed(
    monkeypatch: pytest.MonkeyPatch, provider: OIDCIdentityProvider
) -> None:
    from jwt.exceptions import PyJWKClientConnectionError

    key = _new_rsa_key()
    url = _unique_jwks_url()
    _configure(monkeypatch, jwks_url=url)

    def _boom(self: PyJWKClient) -> dict[str, Any]:
        raise PyJWKClientConnectionError("simulated network failure")

    monkeypatch.setattr(PyJWKClient, "fetch_data", _boom)
    token = _sign(key, "kid-1")

    with pytest.raises(AuthenticationError) as excinfo:
        provider.authenticate(f"Bearer {token}")
    assert excinfo.value.detail["code"] == "authentication_unavailable"
    assert excinfo.value.status_code == 503


# ---------------------------------------------------------------------------
# 22. JWKS rotation/refetch
# ---------------------------------------------------------------------------
def test_jwks_rotation_refetches_on_unknown_kid(
    monkeypatch: pytest.MonkeyPatch, provider: OIDCIdentityProvider
) -> None:
    old_key = _new_rsa_key()
    new_key = _new_rsa_key()
    url = _unique_jwks_url()
    _configure(monkeypatch, jwks_url=url)
    _patch_jwks_fetch_sequence(
        monkeypatch,
        [
            _jwks_document((old_key, "kid-old")),
            _jwks_document((old_key, "kid-old"), (new_key, "kid-new")),
        ],
    )
    token = _sign(new_key, "kid-new")

    user = provider.authenticate(f"Bearer {token}")

    assert user.user_id == _derive_user_id(ISSUER, "user-123")


# ---------------------------------------------------------------------------
# 23. raw token absent from logs/errors
# ---------------------------------------------------------------------------
def test_raw_token_absent_from_error_detail(
    monkeypatch: pytest.MonkeyPatch, provider: OIDCIdentityProvider
) -> None:
    key = _new_rsa_key()
    url = _unique_jwks_url()
    _configure(monkeypatch, jwks_url=url)
    _patch_jwks_fetch(monkeypatch, _jwks_document((key, "kid-1")))
    token = _sign(key, "kid-1", issuer="https://attacker.test/")

    with pytest.raises(AuthenticationError) as excinfo:
        provider.authenticate(f"Bearer {token}")

    assert token not in str(excinfo.value.detail)
    assert token not in repr(excinfo.value)


# ---------------------------------------------------------------------------
# 24. existing dependency override seam still works
# ---------------------------------------------------------------------------
def test_dependency_override_seam_still_works() -> None:
    from app.auth.identity import AuthenticatedUser

    probe_app = FastAPI()

    @probe_app.get("/probe")
    def probe(user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, str]:
        return {"user_id": str(user.user_id)}

    fixed_user = AuthenticatedUser(user_id=uuid4(), is_platform_admin=True)
    probe_app.dependency_overrides[get_current_user] = lambda: fixed_user
    client = TestClient(probe_app)

    response = client.get("/probe")

    assert response.status_code == 200
    assert response.json()["user_id"] == str(fixed_user.user_id)


# ---------------------------------------------------------------------------
# Security probe L: a live /api/v1/me request with a valid signed token now
# reaches the access layer instead of failing with "Authentication is not
# configured".
# ---------------------------------------------------------------------------
def test_live_me_endpoint_accepts_valid_token(monkeypatch: pytest.MonkeyPatch) -> None:
    from collections.abc import Generator as _Generator

    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.db.session import Base, get_db
    from app.main import app

    key = _new_rsa_key()
    url = _unique_jwks_url()
    _configure(monkeypatch, jwks_url=url)
    _patch_jwks_fetch(monkeypatch, _jwks_document((key, "kid-1")))
    token = _sign(key, "kid-1")

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
    assert body["user_id"] == str(_derive_user_id(ISSUER, "user-123"))
    assert body["is_platform_admin"] is False
    assert body["memberships"] == []

    unauthenticated = TestClient(app).get("/api/v1/me")
    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["detail"]["code"] == "authentication_required"


# ---------------------------------------------------------------------------
# SBASE-03: Supabase JWT contract (ES256, project-specific issuer, aud
# literal "authenticated"). These mirror the generic RS256 negative tests
# above against the exact algorithm/issuer shape the live provider uses,
# rather than assuming the generic mechanism transfers untested.
# ---------------------------------------------------------------------------
def test_valid_es256_supabase_shaped_jwt_authenticates(
    monkeypatch: pytest.MonkeyPatch, provider: OIDCIdentityProvider
) -> None:
    key = _new_ec_key()
    url = _unique_jwks_url()
    _configure(
        monkeypatch,
        issuer=SUPABASE_ISSUER,
        audience=SUPABASE_AUDIENCE,
        jwks_url=url,
        algorithms="ES256",
    )
    _patch_jwks_fetch(monkeypatch, _jwks_document((key, "kid-1")))
    token = _sign(
        key,
        "kid-1",
        issuer=SUPABASE_ISSUER,
        audience=SUPABASE_AUDIENCE,
        algorithm="ES256",
        subject=str(uuid4()),
        extra_claims={"email": "pilot@example.com", "role": "authenticated"},
    )

    user = provider.authenticate(f"Bearer {token}")

    assert user.email == "pilot@example.com"
    # No top-level email_verified claim in the real Supabase contract (per
    # SBASE-01) -- must resolve to False, never inferred from anything else.
    assert user.email_verified is False
    assert user.is_platform_admin is False


def test_wrong_supabase_project_issuer_rejected(
    monkeypatch: pytest.MonkeyPatch, provider: OIDCIdentityProvider
) -> None:
    """A token from a *different* Supabase project must be rejected purely
    on issuer mismatch -- proving issuer, not the literal "authenticated"
    audience, is what actually binds Core to its configured project."""
    key = _new_ec_key()
    url = _unique_jwks_url()
    _configure(
        monkeypatch,
        issuer=SUPABASE_ISSUER,
        audience=SUPABASE_AUDIENCE,
        jwks_url=url,
        algorithms="ES256",
    )
    _patch_jwks_fetch(monkeypatch, _jwks_document((key, "kid-1")))
    other_project_issuer = "https://someoneelsesproject.supabase.co/auth/v1"
    token = _sign(
        key,
        "kid-1",
        issuer=other_project_issuer,
        audience=SUPABASE_AUDIENCE,
        algorithm="ES256",
    )

    with pytest.raises(AuthenticationError) as excinfo:
        provider.authenticate(f"Bearer {token}")
    assert excinfo.value.detail["code"] == "authentication_invalid"
    assert excinfo.value.status_code == 401


def test_es256_tampered_signature_rejected(
    monkeypatch: pytest.MonkeyPatch, provider: OIDCIdentityProvider
) -> None:
    key = _new_ec_key()
    url = _unique_jwks_url()
    _configure(
        monkeypatch,
        issuer=SUPABASE_ISSUER,
        audience=SUPABASE_AUDIENCE,
        jwks_url=url,
        algorithms="ES256",
    )
    _patch_jwks_fetch(monkeypatch, _jwks_document((key, "kid-1")))
    token = _sign(
        key, "kid-1", issuer=SUPABASE_ISSUER, audience=SUPABASE_AUDIENCE, algorithm="ES256"
    )
    header, payload, signature = token.split(".")
    tampered = f"{header}.{payload}.{signature[:-2]}{'AA' if signature[-2:] != 'AA' else 'BB'}"

    with pytest.raises(AuthenticationError) as excinfo:
        provider.authenticate(f"Bearer {tampered}")
    assert excinfo.value.detail["code"] == "authentication_invalid"


def test_es256_wrong_signing_key_rejected(
    monkeypatch: pytest.MonkeyPatch, provider: OIDCIdentityProvider
) -> None:
    trusted_key = _new_ec_key()
    attacker_key = _new_ec_key()
    url = _unique_jwks_url()
    _configure(
        monkeypatch,
        issuer=SUPABASE_ISSUER,
        audience=SUPABASE_AUDIENCE,
        jwks_url=url,
        algorithms="ES256",
    )
    _patch_jwks_fetch(monkeypatch, _jwks_document((trusted_key, "kid-1")))
    token = _sign(
        attacker_key,
        "kid-1",
        issuer=SUPABASE_ISSUER,
        audience=SUPABASE_AUDIENCE,
        algorithm="ES256",
    )

    with pytest.raises(AuthenticationError) as excinfo:
        provider.authenticate(f"Bearer {token}")
    assert excinfo.value.detail["code"] == "authentication_invalid"


def test_rs256_token_rejected_when_only_es256_configured(
    monkeypatch: pytest.MonkeyPatch, provider: OIDCIdentityProvider
) -> None:
    """A deployment configured for Supabase's ES256 must not accidentally
    still accept an RS256 (e.g. stale Auth0-shaped) token."""
    key = _new_rsa_key()
    url = _unique_jwks_url()
    _configure(
        monkeypatch,
        issuer=SUPABASE_ISSUER,
        audience=SUPABASE_AUDIENCE,
        jwks_url=url,
        algorithms="ES256",
    )
    _patch_jwks_fetch(monkeypatch, _jwks_document((key, "kid-1")))
    token = _sign(
        key,
        "kid-1",
        issuer=SUPABASE_ISSUER,
        audience=SUPABASE_AUDIENCE,
        algorithm="RS256",
    )

    with pytest.raises(AuthenticationError) as excinfo:
        provider.authenticate(f"Bearer {token}")
    assert excinfo.value.detail["code"] == "authentication_invalid"


def test_es256_expired_jwt_rejected(
    monkeypatch: pytest.MonkeyPatch, provider: OIDCIdentityProvider
) -> None:
    key = _new_ec_key()
    url = _unique_jwks_url()
    _configure(
        monkeypatch,
        issuer=SUPABASE_ISSUER,
        audience=SUPABASE_AUDIENCE,
        jwks_url=url,
        algorithms="ES256",
    )
    _patch_jwks_fetch(monkeypatch, _jwks_document((key, "kid-1")))
    token = _sign(
        key,
        "kid-1",
        issuer=SUPABASE_ISSUER,
        audience=SUPABASE_AUDIENCE,
        algorithm="ES256",
        expires_in=-60,
    )

    with pytest.raises(AuthenticationError) as excinfo:
        provider.authenticate(f"Bearer {token}")
    assert excinfo.value.detail["code"] == "authentication_invalid"


# ---------------------------------------------------------------------------
# SBASE-03 requirement 9 (A, B): a cryptographically valid, Supabase-shaped
# token resolves through the REAL identity provider (not the IdentityState
# test double used elsewhere in the suite) into Core's real membership/RBAC
# model -- authenticated-but-no-workspace when no membership exists, and the
# correct organization/role once one does. Tenant isolation and insufficient-
# role 403 (C, D) are exercised extensively elsewhere in the suite against
# the same AuthenticatedUser contract this real-JWT path also produces, so
# they are not duplicated here with full JWT plumbing.
# ---------------------------------------------------------------------------
def _real_jwt_test_client(monkeypatch: pytest.MonkeyPatch) -> tuple[Any, Any, str, Any]:
    from collections.abc import Generator as _Generator

    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.db.session import Base, get_db
    from app.main import app

    key = _new_ec_key()
    url = _unique_jwks_url()
    _configure(
        monkeypatch,
        issuer=SUPABASE_ISSUER,
        audience=SUPABASE_AUDIENCE,
        jwks_url=url,
        algorithms="ES256",
    )
    _patch_jwks_fetch(monkeypatch, _jwks_document((key, "kid-1")))
    subject = str(uuid4())
    token = _sign(
        key,
        "kid-1",
        issuer=SUPABASE_ISSUER,
        audience=SUPABASE_AUDIENCE,
        algorithm="ES256",
        subject=subject,
        extra_claims={"email": "pilot@example.com"},
    )

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
    return app, engine, token, factory


def test_real_supabase_jwt_with_no_membership_yields_no_workspace_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.db.session import get_db

    app, engine, token, _factory = _real_jwt_test_client(monkeypatch)
    try:
        with TestClient(app) as client:
            me = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
            context = client.get("/api/v1/me/context", headers={"Authorization": f"Bearer {token}"})
    finally:
        app.dependency_overrides.pop(get_db, None)
        from app.db.session import Base

        Base.metadata.drop_all(engine)
        engine.dispose()

    assert me.status_code == 200
    assert me.json()["memberships"] == []
    assert context.status_code == 200
    assert context.json()["state"] == "no_membership"


def test_real_supabase_jwt_with_membership_resolves_org_and_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from uuid import UUID

    from app.db.session import get_db
    from app.models.entities import MembershipRole, MembershipStatus
    from app.schemas.contracts import OrganizationCreate
    from app.schemas.memberships import MembershipCreate
    from app.services.membership_service import OrganizationMembershipService
    from app.services.organization_service import OrganizationService

    app, engine, token, factory = _real_jwt_test_client(monkeypatch)
    try:
        header, payload_b64, _sig = token.split(".")
        import base64 as _b64

        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        claims = json.loads(_b64.urlsafe_b64decode(padded))
        user_id = _derive_user_id(claims["iss"], claims["sub"])

        with factory() as session:
            org = OrganizationService().create(
                session,
                OrganizationCreate(
                    name="Real JWT Org",
                    slug="real-jwt-org",
                    country_code="US",
                    default_currency="USD",
                    timezone="UTC",
                ),
            )
            OrganizationMembershipService().create(
                session,
                org.id,
                MembershipCreate(
                    user_id=user_id,
                    role=MembershipRole.ORGANIZATION_ADMIN,
                    status=MembershipStatus.ACTIVE,
                ),
                invited_by_user_id=UUID(int=0),
            )
            session.commit()

        with TestClient(app) as client:
            context = client.get("/api/v1/me/context", headers={"Authorization": f"Bearer {token}"})
    finally:
        app.dependency_overrides.pop(get_db, None)
        from app.db.session import Base

        Base.metadata.drop_all(engine)
        engine.dispose()

    assert context.status_code == 200
    body = context.json()
    assert body["state"] == "active"
    assert body["role"] == MembershipRole.ORGANIZATION_ADMIN.value
    assert body["organization"]["slug"] == "real-jwt-org"
