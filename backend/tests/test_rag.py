"""M1 — RAG 抽象层单测。

只测注册表 + 路由结构 + markdown 切段，不真打 embedding（避免下载模型）。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings
from app.rag.embeddings import (
    EMBEDDING_REGISTRY,
    EmbeddingProviderConfig,
    list_embedding_providers,
)
from app.rag.ingest import _split_markdown_by_h2  # type: ignore[attr-defined]


# -----------------------------------------------------------------------------
# Embedding 注册表
# -----------------------------------------------------------------------------
EXPECTED_PROVIDERS = {"huggingface", "openai", "qwen"}


def test_registry_has_all_expected_providers():
    assert EXPECTED_PROVIDERS.issubset(set(EMBEDDING_REGISTRY.keys()))


def test_registry_entries_have_full_config():
    for name, cfg in EMBEDDING_REGISTRY.items():
        assert isinstance(cfg, EmbeddingProviderConfig)
        assert cfg.name == name
        assert cfg.display_name
        assert cfg.adapter in {"huggingface", "openai", "dashscope"}
        assert cfg.default_model
        assert cfg.dimensions and cfg.dimensions > 0


def test_huggingface_does_not_require_api_key():
    cfg = EMBEDDING_REGISTRY["huggingface"]
    assert cfg.api_key_field is None


def test_openai_qwen_require_api_keys():
    assert EMBEDDING_REGISTRY["openai"].api_key_field == "openai_api_key"
    assert EMBEDDING_REGISTRY["qwen"].api_key_field == "dashscope_api_key"


def test_list_providers_marks_local_as_configured(monkeypatch):
    """本地 huggingface 没 api_key_field，应永远 configured=True。"""
    monkeypatch.setenv("EMBEDDING_PROVIDER", "huggingface")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()

    by_name = {p["name"]: p for p in list_embedding_providers()}
    assert by_name["huggingface"]["configured"] is True
    assert by_name["huggingface"]["is_active"] is True
    assert by_name["openai"]["configured"] is False

    get_settings.cache_clear()


def test_active_provider_switches(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake")
    get_settings.cache_clear()

    by_name = {p["name"]: p for p in list_embedding_providers()}
    assert by_name["openai"]["is_active"] is True
    assert by_name["openai"]["configured"] is True
    assert by_name["huggingface"]["is_active"] is False

    get_settings.cache_clear()


# -----------------------------------------------------------------------------
# Markdown 切段
# -----------------------------------------------------------------------------
def test_split_markdown_by_h2_basic():
    md = """# 顶层标题

前言段，应该被丢弃或挂到第一个 H2 之后。

## 第一节

第一节内容。

## 第二节

第二节内容。
"""
    sections = _split_markdown_by_h2(md)
    assert len(sections) == 2
    assert sections[0][0] == "第一节"
    assert "第一节内容" in sections[0][1]
    assert sections[1][0] == "第二节"


def test_split_markdown_no_h2():
    md = "纯文本，没有 H2 标题。"
    sections = _split_markdown_by_h2(md)
    assert len(sections) == 1
    assert sections[0][0] == ""
    assert sections[0][1] == md.strip()


def test_split_real_domain_knowledge():
    """跑一遍真实的 domain_knowledge.md，确保切段无报错。"""
    p = Path(__file__).resolve().parent.parent / "domain_knowledge.md"
    if not p.exists():
        return  # CI 上文件可能不在
    sections = _split_markdown_by_h2(p.read_text(encoding="utf-8"))
    # 至少切出 5 段
    assert len(sections) >= 5
    titles = [t for t, _ in sections]
    # 含核心主题
    assert any("单位" in t for t in titles)
    assert any("Sector" in t or "行业" in t for t in titles)
