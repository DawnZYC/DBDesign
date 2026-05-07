"""应用配置：从环境变量加载（.env 自动支持）。"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置。所有字段都能由环境变量覆盖。"""

    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/ecotea",
        description="SQLAlchemy 数据库连接 URL（建议 psycopg v3）。",
    )
    allowed_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        description="CORS 允许的前端 origin，逗号分隔。",
    )
    log_level: str = Field(default="INFO", description="日志级别。")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @property
    def cors_origins(self) -> list[str]:
        """把逗号分隔字符串切成列表。"""
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """单例模式取配置，避免重复读 .env。"""
    return Settings()
