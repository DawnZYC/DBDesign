"""LLM provider abstraction layer — registry pattern + factory.

Supported providers:
  - openai     (default): https://api.openai.com/v1
  - deepseek           : https://api.deepseek.com/v1            (OpenAI-compatible)
  - qwen / dashscope   : https://dashscope.aliyuncs.com/...      (OpenAI-compatible)
  - moonshot / kimi    : https://api.moonshot.cn/v1              (OpenAI-compatible)
  - zhipu / glm        : https://open.bigmodel.cn/api/paas/v4/   (OpenAI-compatible)
  - anthropic          : standalone SDK (langchain-anthropic)

Adding a new provider only requires:
  1. Add an entry to PROVIDER_REGISTRY
  2. Add the corresponding *_API_KEY field in app/config.py
"""

from __future__ import annotations

import logging
import time
from typing import Any, Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from app.config import get_settings

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Provider config card
# -----------------------------------------------------------------------------
class ProviderConfig(BaseModel):
    """Config card for a single provider (immutable)."""

    name: str
    display_name: str
    adapter: Literal["openai_compat", "anthropic"]
    api_key_field: str  # the corresponding field name on Settings
    base_url: str | None = (
        None  # set for OpenAI-compatible; None uses the default (official OpenAI)
    )
    default_model: str
    docs_url: str | None = None


# To add a new provider, append one entry here.
PROVIDER_REGISTRY: dict[str, ProviderConfig] = {
    "openai": ProviderConfig(
        name="openai",
        display_name="OpenAI",
        adapter="openai_compat",
        api_key_field="openai_api_key",
        base_url=None,
        default_model="gpt-4o-mini",
        docs_url="https://platform.openai.com/docs/models",
    ),
    "deepseek": ProviderConfig(
        name="deepseek",
        display_name="DeepSeek",
        adapter="openai_compat",
        api_key_field="deepseek_api_key",
        base_url="https://api.deepseek.com/v1",
        default_model="deepseek-chat",
        docs_url="https://api-docs.deepseek.com/",
    ),
    "qwen": ProviderConfig(
        name="qwen",
        display_name="Tongyi Qianwen (DashScope)",
        adapter="openai_compat",
        api_key_field="dashscope_api_key",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        default_model="qwen-plus",
        docs_url="https://help.aliyun.com/zh/model-studio/getting-started/models",
    ),
    "moonshot": ProviderConfig(
        name="moonshot",
        display_name="Moonshot Kimi",
        adapter="openai_compat",
        api_key_field="moonshot_api_key",
        base_url="https://api.moonshot.cn/v1",
        default_model="moonshot-v1-8k",
        docs_url="https://platform.moonshot.cn/docs/api/",
    ),
    "zhipu": ProviderConfig(
        name="zhipu",
        display_name="Zhipu GLM",
        adapter="openai_compat",
        api_key_field="zhipu_api_key",
        base_url="https://open.bigmodel.cn/api/paas/v4/",
        default_model="glm-4-plus",
        docs_url="https://open.bigmodel.cn/dev/api",
    ),
    "anthropic": ProviderConfig(
        name="anthropic",
        display_name="Anthropic Claude",
        adapter="anthropic",
        api_key_field="anthropic_api_key",
        base_url=None,
        default_model="claude-3-5-haiku-latest",
        docs_url="https://docs.anthropic.com/en/docs/about-claude/models",
    ),
}


# -----------------------------------------------------------------------------
# Factory function
# -----------------------------------------------------------------------------
def get_chat_model(
    *,
    provider: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> BaseChatModel:
    """Return a ChatModel instance from the current config or explicit arguments.

    Priority (high -> low):
        explicit args > environment variables (.env) > provider default
    """
    settings = get_settings()
    provider_name = (provider or settings.llm_provider or "openai").lower()

    if provider_name not in PROVIDER_REGISTRY:
        raise ValueError(
            f"Unknown provider '{provider_name}'. Options: {', '.join(PROVIDER_REGISTRY.keys())}"
        )
    cfg = PROVIDER_REGISTRY[provider_name]

    api_key = getattr(settings, cfg.api_key_field, None)
    if not api_key:
        raise RuntimeError(
            f"Environment variable {cfg.api_key_field.upper()} is not set; "
            f"cannot initialize provider '{provider_name}'. "
            f"Please add the corresponding API key to .env."
        )

    final_model = model or settings.llm_model or cfg.default_model
    final_temp = temperature if temperature is not None else settings.llm_temperature
    final_max_tokens = max_tokens if max_tokens is not None else settings.llm_max_tokens

    logger.info(
        "Init LLM provider=%s adapter=%s model=%s base_url=%s",
        cfg.name,
        cfg.adapter,
        final_model,
        cfg.base_url or "(default)",
    )

    if cfg.adapter == "openai_compat":
        return _build_openai_compat(
            cfg=cfg,
            api_key=api_key,
            model=final_model,
            temperature=final_temp,
            timeout=settings.llm_timeout_seconds,
            max_tokens=final_max_tokens,
        )
    if cfg.adapter == "anthropic":
        return _build_anthropic(
            api_key=api_key,
            model=final_model,
            temperature=final_temp,
            timeout=settings.llm_timeout_seconds,
            max_tokens=final_max_tokens,
        )
    raise ValueError(f"Unimplemented adapter '{cfg.adapter}'")


def _build_openai_compat(
    *,
    cfg: ProviderConfig,
    api_key: str,
    model: str,
    temperature: float,
    timeout: int,
    max_tokens: int | None,
) -> BaseChatModel:
    """OpenAI protocol / compatible (DeepSeek / Qwen / Moonshot / Zhipu)."""
    from langchain_openai import ChatOpenAI  # lazy import to avoid a hard dependency

    kwargs: dict[str, Any] = {
        "model": model,
        "api_key": api_key,
        "temperature": temperature,
        "timeout": timeout,
    }
    if cfg.base_url:
        kwargs["base_url"] = cfg.base_url
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    return ChatOpenAI(**kwargs)


def _build_anthropic(
    *,
    api_key: str,
    model: str,
    temperature: float,
    timeout: int,
    max_tokens: int | None,
) -> BaseChatModel:
    """Anthropic Claude (standalone SDK)."""
    from langchain_anthropic import ChatAnthropic

    kwargs: dict[str, Any] = {
        "model": model,
        "api_key": api_key,
        "temperature": temperature,
        "timeout": timeout,
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    return ChatAnthropic(**kwargs)


# -----------------------------------------------------------------------------
# Metadata queries
# -----------------------------------------------------------------------------
def list_available_providers() -> list[dict[str, Any]]:
    """Enumerate all providers, marking whether an API key is configured and whether each is active."""
    settings = get_settings()
    active = (settings.llm_provider or "openai").lower()
    out: list[dict[str, Any]] = []
    for cfg in PROVIDER_REGISTRY.values():
        configured = bool(getattr(settings, cfg.api_key_field, None))
        out.append(
            {
                "name": cfg.name,
                "display_name": cfg.display_name,
                "adapter": cfg.adapter,
                "default_model": cfg.default_model,
                "base_url": cfg.base_url,
                "docs_url": cfg.docs_url,
                "configured": configured,
                "is_active": cfg.name == active,
            }
        )
    return out


def test_connectivity(provider: str | None = None) -> dict[str, Any]:
    """Make a minimal request to the current / given provider, for health checks.

    Returns {ok, latency_ms?, error?, provider, model}.
    Never raises; all errors collapse into ok=False.
    """
    settings = get_settings()
    provider_name = (provider or settings.llm_provider or "openai").lower()
    info: dict[str, Any] = {
        "provider": provider_name,
        "model": None,
        "ok": False,
    }
    try:
        cfg = PROVIDER_REGISTRY.get(provider_name)
        if cfg is None:
            info["error"] = f"unknown provider: {provider_name}"
            return info
        info["model"] = settings.llm_model or cfg.default_model

        llm = get_chat_model(provider=provider_name)
        start = time.perf_counter()
        # Tiny request + tiny output to avoid cost
        result = llm.invoke([HumanMessage(content="ping")])
        info["latency_ms"] = int((time.perf_counter() - start) * 1000)
        info["ok"] = True
        if hasattr(result, "content"):
            preview = (
                str(result.content)[:60]
                if isinstance(result.content, str)
                else str(result.content)[:60]
            )
            info["response_preview"] = preview
    except Exception as exc:  # noqa: BLE001
        info["error"] = f"{type(exc).__name__}: {exc!s}"
    return info
