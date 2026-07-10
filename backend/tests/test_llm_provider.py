"""M0 — LLM provider abstraction layer unit tests.

Note: these tests never hit the real LLM API; they only verify:
  - PROVIDER_REGISTRY completeness (the expected providers are registered)
  - get_chat_model factory inputs / exception branches
  - list_available_providers return structure

For a live integration test (real API), add the marker: @pytest.mark.live
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Make the app package importable (works when running pytest standalone)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Force no external dependency: blank out the real API key (prevent accidental CI calls)
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
# Registry completeness
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
    """OpenAI should not set base_url (let the SDK use its default)."""
    assert PROVIDER_REGISTRY["openai"].base_url is None


def test_compatible_providers_have_explicit_base_url():
    """OpenAI-compatible providers must set an explicit base_url."""
    for name in {"deepseek", "qwen", "moonshot", "zhipu"}:
        cfg = PROVIDER_REGISTRY[name]
        assert cfg.adapter == "openai_compat"
        assert cfg.base_url and cfg.base_url.startswith("http")


# -----------------------------------------------------------------------------
# Factory exception branches
# -----------------------------------------------------------------------------
def test_unknown_provider_raises(monkeypatch):
    """An unknown provider name should raise immediately."""
    monkeypatch.setenv("LLM_PROVIDER", "nonexistent")
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="Unknown provider"):
        get_chat_model()
    get_settings.cache_clear()


def test_missing_api_key_raises(monkeypatch):
    """When the API key is not configured, get_chat_model should raise RuntimeError."""
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
# get_chat_model success path (fake key, but constructs a ChatOpenAI object — no real API call)
# -----------------------------------------------------------------------------
def test_construct_openai_chat_model(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake")
    monkeypatch.setenv("LLM_MODEL", "")
    get_settings.cache_clear()

    llm = get_chat_model()
    # The class name being ChatOpenAI is enough (no API call)
    assert "ChatOpenAI" in type(llm).__name__
    assert llm.model_name == "gpt-4o-mini"  # provider default

    get_settings.cache_clear()


def test_construct_deepseek_uses_custom_base_url(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-test")
    get_settings.cache_clear()

    llm = get_chat_model()
    assert "ChatOpenAI" in type(llm).__name__
    # base_url should be passed through
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
