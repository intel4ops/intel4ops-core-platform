from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app as live_app

NAVIGATOR_ORIGIN = "https://intelops-navigator.lovable.app"
UNLISTED_ORIGIN = "https://evil.example"
LOCAL_DEV_ORIGIN = "http://localhost:5173"


def _harness(allow_origins: list[str]) -> TestClient:
    """A minimal app wired the same way app/main.py wires CORSMiddleware,
    so origin-list scenarios can be tested without depending on the process
    environment app.main was imported under."""
    harness = FastAPI()
    harness.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @harness.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return TestClient(harness)


# ---------------------------------------------------------------------------
# Settings.cors_origin_list: production-safe defaults
# ---------------------------------------------------------------------------


def test_cors_origin_list_explicit_configuration_is_used_verbatim() -> None:
    settings = Settings(
        app_env="production",
        cors_origins=f"{NAVIGATOR_ORIGIN}, https://app.intel4ops.com",
    )
    assert settings.cors_origin_list == [NAVIGATOR_ORIGIN, "https://app.intel4ops.com"]


def test_cors_origin_list_defaults_to_no_origins_in_production() -> None:
    settings = Settings(app_env="production", cors_origins="")
    assert settings.cors_origin_list == []


def test_cors_origin_list_falls_back_to_local_dev_origins_when_non_production() -> None:
    settings = Settings(app_env="development", cors_origins="")
    assert settings.cors_origin_list == ["http://localhost:5173", "http://127.0.0.1:5173"]


def test_cors_origin_list_never_injects_a_wildcard_default() -> None:
    # Our own default-selection logic (production -> [], non-production ->
    # local dev origins) must never fall back to "*" on its own. Whether an
    # operator-configured literal "*" is rejected is CORSMiddleware/browser
    # -spec behavior, out of scope for this unit test.
    for app_env in ("development", "production", "pilot"):
        settings = Settings(app_env=app_env, cors_origins="")
        assert "*" not in settings.cors_origin_list


# ---------------------------------------------------------------------------
# Live app wiring: no wildcard, credentials allowed, explicit origins only
# ---------------------------------------------------------------------------


def test_live_app_cors_middleware_has_no_wildcard_origin() -> None:
    cors_entry = next(m for m in live_app.user_middleware if m.cls is CORSMiddleware)
    allow_origins = cors_entry.kwargs["allow_origins"]
    assert isinstance(allow_origins, list)
    assert "*" not in allow_origins
    assert cors_entry.kwargs["allow_credentials"] is True


# ---------------------------------------------------------------------------
# Functional behavior: allowed Navigator origin, denied unlisted origin,
# local dev origin allowed when configured.
# ---------------------------------------------------------------------------


def test_allowed_navigator_origin_receives_cors_headers() -> None:
    client = _harness([NAVIGATOR_ORIGIN])
    response = client.get("/api/v1/health", headers={"Origin": NAVIGATOR_ORIGIN})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == NAVIGATOR_ORIGIN


def test_unlisted_origin_does_not_receive_cors_headers() -> None:
    client = _harness([NAVIGATOR_ORIGIN])
    response = client.get("/api/v1/health", headers={"Origin": UNLISTED_ORIGIN})
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_local_dev_origin_allowed_when_configured() -> None:
    client = _harness([LOCAL_DEV_ORIGIN, "http://127.0.0.1:5173"])
    response = client.get("/api/v1/health", headers={"Origin": LOCAL_DEV_ORIGIN})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == LOCAL_DEV_ORIGIN


def test_preflight_for_multipart_upload_with_authorization_header_is_allowed() -> None:
    client = _harness([NAVIGATOR_ORIGIN])
    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": NAVIGATOR_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == NAVIGATOR_ORIGIN
    assert response.headers.get("access-control-allow-headers") is not None
