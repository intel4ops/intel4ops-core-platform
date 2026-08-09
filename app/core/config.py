from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Intel4Ops Core Platform"
    app_env: str = "development"
    database_url: str = "postgresql+psycopg://intel4ops:intel4ops@localhost:5432/intel4ops"
    cors_origins: str = "http://localhost:5173"

    ai_enabled: bool = False
    ai_provider: str = "openai"
    ai_model: str = "gpt-5.6-terra"
    ai_api_key: str | None = None
    ai_timeout_seconds: float = Field(default=20.0, gt=0, le=120)
    ai_max_input_chars: int = Field(default=24_000, ge=1_000, le=100_000)
    ai_max_excerpt_chars: int = Field(default=0, ge=0, le=2_000)
    ai_max_output_tokens: int = Field(default=4_000, ge=100, le=16_000)
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

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def oidc_allowed_algorithm_list(self) -> list[str]:
        return [item.strip() for item in self.oidc_allowed_algorithms.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
