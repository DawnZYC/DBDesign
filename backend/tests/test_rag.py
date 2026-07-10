"""M1 — RAG abstraction layer unit tests.

Only tests the registry + routing structure + markdown splitting; no real embedding (avoids downloading a model).
"""

from __future__ import annotations

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
# Embedding registry
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
    """Local huggingface has no api_key_field, so it should always be configured=True."""
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
# Markdown splitting
# -----------------------------------------------------------------------------
def test_split_markdown_by_h2_basic():
    md = """# Top-level title

Preamble paragraph, should be dropped or attached after the first H2.

## Section one

Content of section one.

## Section two

Content of section two.
"""
    sections = _split_markdown_by_h2(md)
    assert len(sections) == 2
    assert sections[0][0] == "Section one"
    assert "Content of section one" in sections[0][1]
    assert sections[1][0] == "Section two"


def test_split_markdown_no_h2():
    md = "Plain text, no H2 headings."
    sections = _split_markdown_by_h2(md)
    assert len(sections) == 1
    assert sections[0][0] == ""
    assert sections[0][1] == md.strip()


def test_split_real_domain_knowledge():
    """Run against the real domain_knowledge.md to ensure splitting raises no errors."""
    p = Path(__file__).resolve().parent.parent / "data" / "domain_knowledge.md"
    if not p.exists():
        return  # the file may be absent in CI
    sections = _split_markdown_by_h2(p.read_text(encoding="utf-8"))
    # At least 5 sections
    assert len(sections) >= 5
    titles = [t for t, _ in sections]
    # Contains the core topics
    assert any("Unit" in t for t in titles)
    assert any("Sector" in t for t in titles)
