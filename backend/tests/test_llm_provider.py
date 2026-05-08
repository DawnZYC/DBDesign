"""M0 — LLM Provider 抽象层单测。

注意：这些测试不会真打 LLM API，只验证：
  - PROVIDER_REGISTRY 完整性（注册了预期的 provider）
  - get_chat_model 工厂的入参 / 异常分支
  - list_available_providers 返回结构

如要做 live 集成测试（真打 API），加 marker：@pytest.mark.live
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# 让 app 包可以被 import（独立运行 pytest 时也行）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 强制无外部依赖：屏蔽真实 API key（防止 CI 误打）
os.environ.setdefault("OPENAI_API_KEY", "")

import pytest  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.llm import (  # noqa: E402
    PROVIDER_REGISTRY,
    ProviderConfig,
    get_chat_model,
    list_available_providers,
)


# -----------------------------------------------------------------------------
# Registry 完整性
# -----------------------------------------------------------------------------
EXPECTED_PROVIDERS = {"openai", "deepseek", "qwen", "moonshot", "zhipu", "anthropic"}


def test_registry_has_all_expected_providers():
    assert EXPECTED_PROVIDERS.issubset(set(PROVIDER_REGISTRY.keys()))


def test_registry_entries_have_full_config():
    for name, cfg in PROVIDER_REGISTRY.items():
        assert isinstance(cfg, ProviderConfig)
        assert cfg.name == name
        assert cfg.display_name
        assert cfg.adapter in {"openai_compat", "anthropic"}
        assert cfg.api_key_field.endswith("_api_key")
        assert cfg.default_model


def test_openai_uses_default_base_url():
    """OpenAI 不应设 base_url（让 SDK 走默认值）。"""
    assert PROVIDER_REGISTRY["openai"].base_url is None


def test_compatible_providers_have_explicit_base_url():
    """OpenAI 兼容的国产 provider 必须显式 base_url。"""
    for name in {"deepseek", "qwen", "moonshot", "zhipu"}:
        cfg = PROVIDER_REGISTRY[name]
        assert cfg.adapter == "openai_compat"
        assert cfg.base_url and cfg.base_url.startswith("http")


# -----------------------------------------------------------------------------
# 工厂异常分支
# -----------------------------------------------------------------------------
def test_unknown_provider_raises(monkeypatch):
    """未知 provider 名要立即报错。"""
    monkeypatch.setenv("LLM_PROVIDER", "nonexistent")
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="未知 provider"):
        get_chat_model()
    get_settings.cache_clear()


def test_missing_api_key_raises(monkeypatch):
    """API key 未配置时 get_chat_model 应抛 RuntimeError。"""
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        get_chat_model()
    get_settings.cache_clear()


# -----------------------------------------------------------------------------
# list_available_providers
# -----------------------------------------------------------------------------
def test_list_providers_returns_all(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    get_settings.cache_clear()

    items = list_available_providers()
    names = {it["name"] for it in items}
    assert names == EXPECTED_PROVIDERS

    by_name = {it["name"]: it for it in items}
    assert by_name["openai"]["configured"] is True
    assert by_name["openai"]["is_active"] is True
    assert by_name["deepseek"]["configured"] is False
    assert by_name["deepseek"]["is_active"] is False

    get_settings.cache_clear()


def test_active_provider_marked_correctly(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-fake")
    get_settings.cache_clear()

    by_name = {it["name"]: it for it in list_available_providers()}
    assert by_name["deepseek"]["is_active"] is True
    assert by_name["openai"]["is_active"] is False

    get_settings.cache_clear()


# -----------------------------------------------------------------------------
# get_chat_model 成功路径（用假 key，但能成功构造 ChatOpenAI 对象 — 不真调 API）
# -----------------------------------------------------------------------------
def test_construct_openai_chat_model(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake")
    monkeypatch.setenv("LLM_MODEL", "")
    get_settings.cache_clear()

    llm = get_chat_model()
    # 类名是 ChatOpenAI 即可（不调 API）
    assert "ChatOpenAI" in type(llm).__name__
    assert llm.model_name == "gpt-4o-mini"  # provider 默认

    get_settings.cache_clear()


def test_construct_deepseek_uses_custom_base_url(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-test")
    get_settings.cache_clear()

    llm = get_chat_model()
    assert "ChatOpenAI" in type(llm).__name__
    # base_url 应被透传
    assert "deepseek.com" in str(llm.openai_api_base)

    get_settings.cache_clear()


def test_construct_qwen_uses_dashscope_base_url(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "qwen")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "ds-fake")
    get_settings.cache_clear()

    llm = get_chat_model()
    assert "ChatOpenAI" in type(llm).__name__
    assert "dashscope" in str(llm.openai_api_base)

    get_settings.cache_clear()


def test_explicit_model_override(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake")
    get_settings.cache_clear()

    llm = get_chat_model(model="gpt-4o")
    assert llm.model_name == "gpt-4o"

    get_settings.cache_clear()
