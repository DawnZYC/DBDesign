"""LLM Provider 抽象层 — 注册表模式 + 工厂。

支持的 provider:
  - openai     (默认): https://api.openai.com/v1
  - deepseek          : https://api.deepseek.com/v1            (OpenAI 兼容)
  - qwen / dashscope  : https://dashscope.aliyuncs.com/...      (OpenAI 兼容)
  - moonshot / kimi   : https://api.moonshot.cn/v1              (OpenAI 兼容)
  - zhipu / glm       : https://open.bigmodel.cn/api/paas/v4/   (OpenAI 兼容)
  - anthropic         : 独立 SDK（langchain-anthropic）

加新 provider 只需：
  1. 在 PROVIDER_REGISTRY 增加一项
  2. 在 app/config.py 增加对应的 *_API_KEY 字段
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
# Provider 配置卡片
# -----------------------------------------------------------------------------
class ProviderConfig(BaseModel):
    """单个 provider 的配置卡片（不可变）。"""

    name: str
    display_name: str
    adapter: Literal["openai_compat", "anthropic"]
    api_key_field: str           # Settings 上对应的字段名
    base_url: str | None = None  # OpenAI-compatible 时填，None 用默认（即官方 OpenAI）
    default_model: str
    docs_url: str | None = None


# 加新 provider 在这里追加一条即可。
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
        display_name="通义千问 (DashScope)",
        adapter="openai_compat",
        api_key_field="dashscope_api_key",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        default_model="qwen-plus",
        docs_url="https://help.aliyun.com/zh/model-studio/getting-started/models",
    ),
    "moonshot": ProviderConfig(
        name="moonshot",
        display_name="月之暗面 Kimi",
        adapter="openai_compat",
        api_key_field="moonshot_api_key",
        base_url="https://api.moonshot.cn/v1",
        default_model="moonshot-v1-8k",
        docs_url="https://platform.moonshot.cn/docs/api/",
    ),
    "zhipu": ProviderConfig(
        name="zhipu",
        display_name="智谱 GLM",
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
# 工厂函数
# -----------------------------------------------------------------------------
def get_chat_model(
    *,
    provider: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> BaseChatModel:
    """按当前配置或显式参数返回 ChatModel 实例。

    优先级（高 → 低）：
        显式入参 > 环境变量 (.env) > provider 默认值
    """
    settings = get_settings()
    provider_name = (provider or settings.llm_provider or "openai").lower()

    if provider_name not in PROVIDER_REGISTRY:
        raise ValueError(
            f"未知 provider '{provider_name}'。"
            f"可选: {', '.join(PROVIDER_REGISTRY.keys())}"
        )
    cfg = PROVIDER_REGISTRY[provider_name]

    api_key = getattr(settings, cfg.api_key_field, None)
    if not api_key:
        raise RuntimeError(
            f"环境变量 {cfg.api_key_field.upper()} 未配置；"
            f"无法初始化 provider '{provider_name}'。"
            f" 请在 .env 中填入对应 API key。"
        )

    final_model = model or settings.llm_model or cfg.default_model
    final_temp = temperature if temperature is not None else settings.llm_temperature
    final_max_tokens = max_tokens if max_tokens is not None else settings.llm_max_tokens

    logger.info(
        "Init LLM provider=%s adapter=%s model=%s base_url=%s",
        cfg.name, cfg.adapter, final_model, cfg.base_url or "(default)",
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
    raise ValueError(f"未实现的 adapter '{cfg.adapter}'")


def _build_openai_compat(
    *,
    cfg: ProviderConfig,
    api_key: str,
    model: str,
    temperature: float,
    timeout: int,
    max_tokens: int | None,
) -> BaseChatModel:
    """OpenAI 协议 / 兼容 (DeepSeek / Qwen / Moonshot / 智谱)。"""
    from langchain_openai import ChatOpenAI  # 延迟 import 避免硬依赖

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
    """Anthropic Claude（独立 SDK）。"""
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
# 元信息查询
# -----------------------------------------------------------------------------
def list_available_providers() -> list[dict[str, Any]]:
    """枚举所有 provider，标记当前是否已配置 API key、是否为活跃 provider。"""
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
    """对当前 / 指定 provider 做最小请求，用于健康检查。

    返回 {ok, latency_ms?, error?, provider, model}
    不抛异常，所有错误折成 ok=False。
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
        # 用极小请求 + 极小输出避免成本
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
