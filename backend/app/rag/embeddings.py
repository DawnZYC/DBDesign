"""Embedding Provider 抽象层 — 与 M0 LLM 同样的注册表 + 工厂模式。

所有 provider 统一实现 langchain_core.embeddings.Embeddings 接口；
业务代码只 import Embeddings 不耦合具体 provider。

支持：
  - huggingface (默认): 本地 sentence-transformers，零成本，离线可用
  - openai           : OpenAI text-embedding-3-small / -large
  - qwen             : 通义千问 DashScope text-embedding-v3
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Literal

from langchain_core.embeddings import Embeddings
from pydantic import BaseModel, ConfigDict

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Provider 配置卡片
# -----------------------------------------------------------------------------
class EmbeddingProviderConfig(BaseModel):
    """单个 embedding provider 的配置卡片。"""

    name: str
    display_name: str
    adapter: Literal["huggingface", "openai", "dashscope"]
    api_key_field: str | None = None  # None 表示不需要 API key（本地）
    default_model: str
    dimensions: int | None = None  # 输出向量维度（用于回归测试和文档）

    model_config = ConfigDict(arbitrary_types_allowed=True)


EMBEDDING_REGISTRY: dict[str, EmbeddingProviderConfig] = {
    "huggingface": EmbeddingProviderConfig(
        name="huggingface",
        display_name="HuggingFace 本地 (sentence-transformers)",
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
        display_name="通义千问 (DashScope)",
        adapter="dashscope",
        api_key_field="dashscope_api_key",
        default_model="text-embedding-v3",
        dimensions=1024,
    ),
}


# -----------------------------------------------------------------------------
# 工厂
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
    # 注意：langchain-community 的 DashScopeEmbeddings 走的是 DashScope 原生协议
    from langchain_community.embeddings import DashScopeEmbeddings
    return DashScopeEmbeddings(model=model, dashscope_api_key=settings.dashscope_api_key)


def get_embedder(*, provider: str | None = None, model: str | None = None) -> Embeddings:
    """按当前配置或显式参数返回 Embeddings 实例。

    优先级：显式入参 > 环境变量 > provider 默认值
    """
    settings = get_settings()
    provider_name = (provider or settings.embedding_provider or "huggingface").lower()

    if provider_name not in EMBEDDING_REGISTRY:
        raise ValueError(
            f"未知 embedding provider '{provider_name}'。"
            f"可选: {', '.join(EMBEDDING_REGISTRY.keys())}"
        )
    cfg = EMBEDDING_REGISTRY[provider_name]

    if cfg.api_key_field:
        api_key = getattr(settings, cfg.api_key_field, None)
        if not api_key:
            raise RuntimeError(
                f"环境变量 {cfg.api_key_field.upper()} 未配置，"
                f"无法初始化 embedding provider '{provider_name}'"
            )

    final_model = model or settings.embedding_model or cfg.default_model
    builder = _BUILDERS.get(cfg.adapter)
    if builder is None:
        raise ValueError(f"未实现的 embedding adapter '{cfg.adapter}'")

    logger.info(
        "Init embedding provider=%s model=%s dim=%s",
        cfg.name, final_model, cfg.dimensions,
    )
    return builder(cfg, settings, final_model)


def list_embedding_providers() -> list[dict[str, Any]]:
    """列出所有 embedding provider 及当前配置状态。"""
    settings = get_settings()
    active = (settings.embedding_provider or "huggingface").lower()
    out: list[dict[str, Any]] = []
    for cfg in EMBEDDING_REGISTRY.values():
        if cfg.api_key_field is None:
            configured = True  # 本地 provider 无需 key
        else:
            configured = bool(getattr(settings, cfg.api_key_field, None))
        out.append({
            "name": cfg.name,
            "display_name": cfg.display_name,
            "adapter": cfg.adapter,
            "default_model": cfg.default_model,
            "dimensions": cfg.dimensions,
            "configured": configured,
            "is_active": cfg.name == active,
        })
    return out
