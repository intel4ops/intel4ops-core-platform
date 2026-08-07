from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Intel4Ops Core Platform"
    app_env: str = "development"
    database_url: str = "postgresql+psycopg://intel4ops:intel4ops@localhost:5432/intel4ops"
    cors_origins: str = "http://localhost:5173"

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
