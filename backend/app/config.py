"""Application configuration loaded from environment variables, with .env support."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Locate backend/.env so it is found no matter which directory uvicorn starts from
_ENV_FILE = Path(__file__).parent.parent / ".env"


class Settings(BaseSettings):
    """Global settings. Every field can be overridden by environment variables."""

    # -------------------------------------------------------------------------
    # Infrastructure
    # -------------------------------------------------------------------------
    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/ecotea",
        description="SQLAlchemy database URL; psycopg v3 is recommended.",
    )
    allowed_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        description="Comma-separated frontend origins allowed by CORS.",
    )
    log_level: str = Field(default="INFO", description="Log level.")

    # -------------------------------------------------------------------------
    # LLM provider abstraction layer (M0)
    #   Main provider is openai; can switch to deepseek / qwen / moonshot / zhipu / anthropic
    #   Registry: app/llm/provider.py::PROVIDER_REGISTRY
    # -------------------------------------------------------------------------
    llm_provider: str = Field(
        default="openai",
        description="Main LLM provider name (openai/deepseek/qwen/moonshot/zhipu/anthropic)",
    )
    llm_model: str | None = Field(
        default=None,
        description="Model name; uses the provider default when empty",
    )
    llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    llm_timeout_seconds: int = Field(default=60, ge=1)
    llm_max_tokens: int | None = Field(default=None)

    # Per-provider API keys (configure as needed; leave unused ones empty)
    openai_api_key: str | None = Field(default=None)
    deepseek_api_key: str | None = Field(default=None)
    dashscope_api_key: str | None = Field(default=None, description="Tongyi Qianwen / Qwen")
    moonshot_api_key: str | None = Field(default=None)
    zhipu_api_key: str | None = Field(default=None, description="Zhipu GLM")
    anthropic_api_key: str | None = Field(default=None)

    # -------------------------------------------------------------------------
    # RAG / vector store (M1)
    #   embedding uses the LangChain Embeddings abstraction; registry: app/rag/embeddings.py
    # -------------------------------------------------------------------------
    embedding_provider: str = Field(
        default="huggingface",
        description="Embedding provider name (huggingface/openai/qwen)",
    )
    embedding_model: str | None = Field(
        default=None,
        description="Embedding model name; uses the provider default when empty",
    )
    chroma_persist_dir: str = Field(
        default="./chroma_data",
        description="ChromaDB persistence directory",
    )
    chroma_collection_name: str = Field(
        default="domain_glossary",
        description="Chroma collection name (domain glossary)",
    )

    # -------------------------------------------------------------------------
    # Agent orchestration (M3)
    #   LangGraph 4-agent graph (Planner -> SQL -> Interpreter -> Visualizer)
    # -------------------------------------------------------------------------
    agent_max_retries: int = Field(
        default=2,
        ge=0,
        le=5,
        description="Max retries back to the Planner after a SQL node failure",
    )
    agent_node_timeout: int = Field(
        default=30,
        ge=5,
        description="Timeout in seconds for a single Agent node",
    )
    agent_trace_enabled: bool = Field(
        default=False,
        description="Whether to enable LangSmith tracing (requires LANGCHAIN_API_KEY)",
    )

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),  # absolute path, independent of the startup directory
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def cors_origins(self) -> list[str]:
        """Split a comma-separated string into a list."""
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings to avoid repeatedly reading .env."""
    return Settings()
