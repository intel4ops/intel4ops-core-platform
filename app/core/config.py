from functools import lru_cache
from uuid import UUID

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Local frontend dev origins used only when CORS_ORIGINS is unset AND
# app_env != "production" -- see Settings.cors_origin_list. Never applied
# in production, where an unset CORS_ORIGINS instead yields no allowed
# origins (fail closed, not fail open).
_DEFAULT_DEV_CORS_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")


class Settings(BaseSettings):
    app_name: str = "Intel4Ops Core Platform"
    app_env: str = "development"
    database_url: str = "postgresql+psycopg://intel4ops:intel4ops@localhost:5432/intel4ops"

    @field_validator("database_url")
    @classmethod
    def _normalize_postgres_driver(cls, value: str) -> str:
        # A managed-Postgres host (e.g. Render) commonly hands out a bare
        # postgres:// or postgresql:// connection string with no driver
        # suffix. SQLAlchemy's default dialect for that bare scheme is
        # psycopg2, which this project never installs -- it depends on
        # psycopg (v3) exclusively (see pyproject.toml). Without this
        # normalization, deployments fail at engine-creation time with
        # ModuleNotFoundError: No module named 'psycopg2', even though the
        # application and its migrations only ever use psycopg3. Any URL
        # that already names a driver (postgresql+psycopg://, sqlite://,
        # etc.) passes through unchanged.
        for bare_prefix in ("postgresql://", "postgres://"):
            if value.startswith(bare_prefix):
                return "postgresql+psycopg://" + value[len(bare_prefix) :]
        return value

    cors_origins: str = ""
    mapping_worker_id: str | None = Field(default=None, max_length=200)
    mapping_worker_poll_interval_seconds: float = Field(default=2.0, gt=0, le=60)
    mapping_worker_heartbeat_interval_seconds: float = Field(default=10.0, gt=0, le=60)
    mapping_worker_stale_threshold_seconds: float = Field(default=60.0, ge=10, le=3600)
    mapping_worker_db_backoff_seconds: float = Field(default=5.0, gt=0, le=300)
    mapping_worker_shutdown_grace_seconds: float = Field(default=30.0, ge=0, le=600)

    ai_enabled: bool = False
    ai_provider: str = "openai"
    ai_model: str = "gpt-5.6-terra"
    ai_api_key: str | None = None
    ai_timeout_seconds: float = Field(default=20.0, gt=0, le=120)
    ai_max_input_chars: int = Field(default=24_000, ge=1_000, le=100_000)
    ai_max_excerpt_chars: int = Field(default=0, ge=0, le=2_000)
    ai_max_output_tokens: int = Field(default=4_000, ge=100, le=16_000)
    ai_narrative_max_input_chars: int = Field(default=16_000, ge=1_000, le=16_000)
    ai_narrative_max_output_tokens: int = Field(default=1_800, ge=100, le=1_800)
    ai_max_inference_items: int = Field(default=25, ge=1, le=25)
    ai_max_clarification_questions: int = Field(default=10, ge=0, le=10)
    ai_retry_ceiling: int = Field(default=1, ge=0, le=2)

    # Provider-neutral OIDC resource-server configuration. All three of
    # issuer/audience/jwks_url must be set for authentication to function;
    # if any is missing, get_current_user() fails closed (401/503) rather
    # than skipping verification. None of these ever come from the request.
    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    oidc_jwks_url: str | None = None
    oidc_allowed_algorithms: str = "RS256"

    # ------------------------------------------------------------------
    # P3.xxA.2 pilot auth bridge. Temporary, environment-gated bearer-token
    # identity used only to unblock a pilot (e.g. SOTRA) before real
    # platform-admin provisioning ships -- see app/auth/pilot_bridge.py for
    # the activation rules. Disabled by default; cannot activate when
    # app_env == "production" regardless of pilot_auth_enabled. No default
    # is provided for pilot_auth_token or pilot_user_id -- both must be
    # explicitly configured per deployment, never hard-coded.
    # ------------------------------------------------------------------
    pilot_auth_enabled: bool = False
    pilot_auth_token: str | None = None
    pilot_user_id: UUID | None = None
    pilot_platform_admin: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        configured = [item.strip() for item in self.cors_origins.split(",") if item.strip()]
        if configured:
            return configured
        if self.app_env == "production":
            return []
        return list(_DEFAULT_DEV_CORS_ORIGINS)

    @property
    def oidc_allowed_algorithm_list(self) -> list[str]:
        return [item.strip() for item in self.oidc_allowed_algorithms.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
