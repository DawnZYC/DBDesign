"""应用配置：从环境变量加载（.env 自动支持）。"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置。所有字段都能由环境变量覆盖。"""

    # -------------------------------------------------------------------------
    # 基础设施
    # -------------------------------------------------------------------------
    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/ecotea",
        description="SQLAlchemy 数据库连接 URL（建议 psycopg v3）。",
    )
    allowed_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        description="CORS 允许的前端 origin，逗号分隔。",
    )
    log_level: str = Field(default="INFO", description="日志级别。")

    # -------------------------------------------------------------------------
    # LLM Provider 抽象层（M0）
    #   主 provider 用 openai；可切到 deepseek / qwen / moonshot / zhipu / anthropic
    #   注册表见 app/llm/provider.py::PROVIDER_REGISTRY
    # -------------------------------------------------------------------------
    llm_provider: str = Field(
        default="openai",
        description="主 LLM provider 名（openai/deepseek/qwen/moonshot/zhipu/anthropic）",
    )
    llm_model: str | None = Field(
        default=None,
        description="模型名；为空时使用 provider 默认值",
    )
    llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    llm_timeout_seconds: int = Field(default=60, ge=1)
    llm_max_tokens: int | None = Field(default=None)

    # 各 provider 的 API key（按需配置，不用的留空）
    openai_api_key: str | None = Field(default=None)
    deepseek_api_key: str | None = Field(default=None)
    dashscope_api_key: str | None = Field(default=None, description="通义千问 / Qwen")
    moonshot_api_key: str | None = Field(default=None)
    zhipu_api_key: str | None = Field(default=None, description="智谱 GLM")
    anthropic_api_key: str | None = Field(default=None)

    # -------------------------------------------------------------------------
    # RAG / 向量库（M1）
    #   embedding 走 LangChain Embeddings 抽象，注册表见 app/rag/embeddings.py
    # -------------------------------------------------------------------------
    embedding_provider: str = Field(
        default="huggingface",
        description="embedding provider 名 (huggingface/openai/qwen)",
    )
    embedding_model: str | None = Field(
        default=None,
        description="embedding 模型名；为空时用 provider 默认值",
    )
    chroma_persist_dir: str = Field(
        default="./chroma_data",
        description="ChromaDB 持久化目录",
    )
    chroma_collection_name: str = Field(
        default="domain_glossary",
        description="Chroma collection 名（领域术语库）",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def cors_origins(self) -> list[str]:
        """把逗号分隔字符串切成列表。"""
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """单例模式取配置，避免重复读 .env。"""
    return Settings()
