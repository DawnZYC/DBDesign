"""Embedding provider abstraction — the same registry + factory pattern as the M0 LLM layer.

All providers implement the langchain_core.embeddings.Embeddings interface; business code
only imports Embeddings and is not coupled to a specific provider.

Supported:
  - huggingface (default): local sentence-transformers, zero cost, works offline
  - openai              : OpenAI text-embedding-3-small / -large
  - qwen                : Tongyi Qianwen DashScope text-embedding-v3
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, Literal

from langchain_core.embeddings import Embeddings
from pydantic import BaseModel, ConfigDict

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Provider config card
# -----------------------------------------------------------------------------
class EmbeddingProviderConfig(BaseModel):
    """Config card for a single embedding provider."""

    name: str
    display_name: str
    adapter: Literal["huggingface", "openai", "dashscope"]
    api_key_field: str | None = None  # None means no API key needed (local)
    default_model: str
    dimensions: int | None = None  # output vector dimension (for regression tests and docs)

    model_config = ConfigDict(arbitrary_types_allowed=True)


EMBEDDING_REGISTRY: dict[str, EmbeddingProviderConfig] = {
    "huggingface": EmbeddingProviderConfig(
        name="huggingface",
        display_name="HuggingFace local (sentence-transformers)",
        adapter="huggingface",
        api_key_field=None,
        default_model="sentence-transformers/all-MiniLM-L6-v2",
        dimensions=384,
    ),
    "openai": EmbeddingProviderConfig(
        name="openai",
        display_name="OpenAI",
        adapter="openai",
        api_key_field="openai_api_key",
        default_model="text-embedding-3-small",
        dimensions=1536,
    ),
    "qwen": EmbeddingProviderConfig(
        name="qwen",
        display_name="Tongyi Qianwen (DashScope)",
        adapter="dashscope",
        api_key_field="dashscope_api_key",
        default_model="text-embedding-v3",
        dimensions=1024,
    ),
}


# -----------------------------------------------------------------------------
# Factory
# -----------------------------------------------------------------------------
_BUILDERS: dict[str, Callable[[EmbeddingProviderConfig, Settings, str], Embeddings]] = {}


def _register_builder(adapter: str):
    def decorator(fn):
        _BUILDERS[adapter] = fn
        return fn

    return decorator


@_register_builder("huggingface")
def _build_hf(cfg: EmbeddingProviderConfig, settings: Settings, model: str) -> Embeddings:
    from langchain_huggingface import HuggingFaceEmbeddings

    return HuggingFaceEmbeddings(model_name=model)


@_register_builder("openai")
def _build_openai(cfg: EmbeddingProviderConfig, settings: Settings, model: str) -> Embeddings:
    from langchain_openai import OpenAIEmbeddings

    return OpenAIEmbeddings(model=model, api_key=settings.openai_api_key)


@_register_builder("dashscope")
def _build_dashscope(cfg: EmbeddingProviderConfig, settings: Settings, model: str) -> Embeddings:
    # Note: langchain-community's DashScopeEmbeddings uses the native DashScope protocol
    from langchain_community.embeddings import DashScopeEmbeddings

    return DashScopeEmbeddings(model=model, dashscope_api_key=settings.dashscope_api_key)


def get_embedder(*, provider: str | None = None, model: str | None = None) -> Embeddings:
    """Return an Embeddings instance from the current config or explicit arguments.

    Priority: explicit args > environment variables > provider default
    """
    settings = get_settings()
    provider_name = (provider or settings.embedding_provider or "huggingface").lower()

    if provider_name not in EMBEDDING_REGISTRY:
        raise ValueError(
            f"Unknown embedding provider '{provider_name}'. "
            f"Options: {', '.join(EMBEDDING_REGISTRY.keys())}"
        )
    cfg = EMBEDDING_REGISTRY[provider_name]

    if cfg.api_key_field:
        api_key = getattr(settings, cfg.api_key_field, None)
        if not api_key:
            raise RuntimeError(
                f"Environment variable {cfg.api_key_field.upper()} is not set; "
                f"cannot initialize embedding provider '{provider_name}'"
            )

    final_model = model or settings.embedding_model or cfg.default_model
    builder = _BUILDERS.get(cfg.adapter)
    if builder is None:
        raise ValueError(f"Unimplemented embedding adapter '{cfg.adapter}'")

    logger.info(
        "Init embedding provider=%s model=%s dim=%s",
        cfg.name,
        final_model,
        cfg.dimensions,
    )
    return builder(cfg, settings, final_model)


def list_embedding_providers() -> list[dict[str, Any]]:
    """List all embedding providers and their current config status."""
    settings = get_settings()
    active = (settings.embedding_provider or "huggingface").lower()
    out: list[dict[str, Any]] = []
    for cfg in EMBEDDING_REGISTRY.values():
        if cfg.api_key_field is None:
            configured = True  # local provider needs no key
        else:
            configured = bool(getattr(settings, cfg.api_key_field, None))
        out.append(
            {
                "name": cfg.name,
                "display_name": cfg.display_name,
                "adapter": cfg.adapter,
                "default_model": cfg.default_model,
                "dimensions": cfg.dimensions,
                "configured": configured,
                "is_active": cfg.name == active,
            }
        )
    return out
