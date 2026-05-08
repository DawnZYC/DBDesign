"""Application configuration loaded from environment variables, with .env support."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Global settings. Every field can be overridden by environment variables."""

    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/ecotea",
        description="SQLAlchemy database URL; psycopg v3 is recommended.",
    )
    allowed_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        description="Comma-separated frontend origins allowed by CORS.",
    )
    log_level: str = Field(default="INFO", description="Log level.")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @property
    def cors_origins(self) -> list[str]:
        """Split a comma-separated string into a list."""
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings to avoid repeatedly reading .env."""
    return Settings()
