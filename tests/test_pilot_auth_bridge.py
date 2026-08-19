from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

import app.auth.identity as identity_module
from app.auth.identity import AuthenticatedUser, get_current_user
from app.auth.pilot_bridge import resolve_pilot_identity
from app.core.config import Settings

PILOT_TOKEN = "pilot-secret-token-for-tests-only"  # noqa: S105 -- test fixture value, not real


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "app_env": "pilot",
        "pilot_auth_enabled": True,
        "pilot_auth_token": PILOT_TOKEN,
        "pilot_user_id": uuid4(),
        "pilot_platform_admin": True,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# resolve_pilot_identity: pure activation-rule tests
# ---------------------------------------------------------------------------


def test_pilot_disabled_by_default() -> None:
    settings = _settings(pilot_auth_enabled=False)
    result = resolve_pilot_identity(settings, f"Bearer {PILOT_TOKEN}")
    assert result is None


@pytest.mark.parametrize("app_env", ["production"])
def test_pilot_never_activates_in_production_even_when_enabled(app_env: str) -> None:
    settings = _settings(app_env=app_env)
    result = resolve_pilot_identity(settings, f"Bearer {PILOT_TOKEN}")
    assert result is None


def test_pilot_missing_token_configuration_returns_none() -> None:
    settings = _settings(pilot_auth_token=None)
    assert resolve_pilot_identity(settings, f"Bearer {PILOT_TOKEN}") is None


def test_pilot_missing_user_id_configuration_returns_none() -> None:
    settings = _settings(pilot_user_id=None)
    assert resolve_pilot_identity(settings, f"Bearer {PILOT_TOKEN}") is None


def test_pilot_missing_authorization_header_returns_none() -> None:
    settings = _settings()
    assert resolve_pilot_identity(settings, None) is None


@pytest.mark.parametrize(
    "header",
    ["", "Bearer", "Bearer ", f"Basic {PILOT_TOKEN}", f"BearerX{PILOT_TOKEN}"],
)
def test_pilot_malformed_header_returns_none(header: str) -> None:
    settings = _settings()
    assert resolve_pilot_identity(settings, header) is None


def test_pilot_wrong_token_returns_none() -> None:
    settings = _settings()
    assert resolve_pilot_identity(settings, "Bearer not-the-configured-token") is None


def test_pilot_valid_token_returns_configured_identity() -> None:
    settings = _settings(pilot_platform_admin=True)
    result = resolve_pilot_identity(settings, f"Bearer {PILOT_TOKEN}")
    assert result == (settings.pilot_user_id, True)


def test_pilot_privileges_are_exactly_what_is_configured_not_implicitly_admin() -> None:
    settings = _settings(pilot_platform_admin=False)
    result = resolve_pilot_identity(settings, f"Bearer {PILOT_TOKEN}")
    assert result == (settings.pilot_user_id, False)


# ---------------------------------------------------------------------------
# get_current_user integration: pilot bridge composes with (never replaces)
# the OIDC path.
# ---------------------------------------------------------------------------


def _probe_app() -> FastAPI:
    probe = FastAPI()

    @probe.get("/probe")
    def probe_route(user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, object]:
        return {"user_id": str(user.user_id), "is_platform_admin": user.is_platform_admin}

    return probe


def test_get_current_user_accepts_valid_pilot_token(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings()
    monkeypatch.setattr(identity_module, "get_settings", lambda: settings)
    client = TestClient(_probe_app())

    response = client.get("/probe", headers={"Authorization": f"Bearer {PILOT_TOKEN}"})

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == str(settings.pilot_user_id)
    assert body["is_platform_admin"] is True


def test_get_current_user_falls_through_to_oidc_when_pilot_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(pilot_auth_enabled=False)
    monkeypatch.setattr(identity_module, "get_settings", lambda: settings)
    client = TestClient(_probe_app())

    response = client.get("/probe", headers={"Authorization": f"Bearer {PILOT_TOKEN}"})

    # Falls through to real OIDC verification, which is unconfigured here,
    # so it fails closed -- never silently grants the pilot identity.
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "authentication_unavailable"


def test_get_current_user_locks_out_pilot_token_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(app_env="production")
    monkeypatch.setattr(identity_module, "get_settings", lambda: settings)
    client = TestClient(_probe_app())

    response = client.get("/probe", headers={"Authorization": f"Bearer {PILOT_TOKEN}"})

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "authentication_unavailable"


def test_get_current_user_rejects_wrong_pilot_token(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings()
    monkeypatch.setattr(identity_module, "get_settings", lambda: settings)
    client = TestClient(_probe_app())

    response = client.get("/probe", headers={"Authorization": "Bearer wrong-token"})

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "authentication_unavailable"


def test_get_current_user_normal_oidc_path_unaffected_when_pilot_fully_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Pilot vars entirely unset (all defaults) -- resolve_pilot_identity must
    # be a no-op, leaving the normal OIDC 401-on-missing-header behavior
    # completely unchanged.
    settings = Settings(
        app_env="development",
        oidc_issuer="https://issuer.test/",
        oidc_audience="test-audience",
        oidc_jwks_url="https://issuer.test/jwks.json",
    )
    monkeypatch.setattr(identity_module, "get_settings", lambda: settings)
    client = TestClient(_probe_app())

    response = client.get("/probe")

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "authentication_required"
