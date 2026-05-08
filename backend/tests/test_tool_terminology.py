"""① lookup_terminology 单测（依赖 DB；RAG 部分用 monkeypatch 替身避免下载模型）。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._db_fixture import setup_test_db  # noqa: E402

setup_test_db()

from app.tools import terminology as term_mod  # noqa: E402


def _stub_rag_search(query: str, k: int = 5):
    """RAG 替身：根据 query 返回固定的"语义命中"。"""
    from app.rag.search import SearchHit
    if "天然气" in query or "natural gas" in query.lower():
        return [SearchHit(
            text="商品代码: PWRNGA | 描述: Power Natural Gas",
            score=0.85,
            metadata={"source": "commodity", "code": "PWRNGA"},
        )]
    if "carbon" in query.lower() or "co2" in query.lower():
        return [SearchHit(
            text="商品代码: PWRCO2 | 描述: Power CO2",
            score=0.78,
            metadata={"source": "commodity", "code": "PWRCO2"},
        )]
    return []


def test_exact_code_lookup_commodity(monkeypatch):
    monkeypatch.setattr(term_mod, "rag_search", _stub_rag_search)
    out = term_mod.lookup_terminology.invoke({"term": "PWRNGA"})
    assert out["matched_by"] == "exact_code"
    assert len(out["hits"]) == 1
    hit = out["hits"][0]
    assert hit["metadata"]["code"] == "PWRNGA"
    assert hit["metadata"]["source"] == "commodity"


def test_exact_code_lookup_sector(monkeypatch):
    monkeypatch.setattr(term_mod, "rag_search", _stub_rag_search)
    out = term_mod.lookup_terminology.invoke({"term": "POWER"})
    assert out["matched_by"] == "exact_code"
    assert out["hits"][0]["metadata"]["source"] == "sector"


def test_exact_code_lookup_geography(monkeypatch):
    monkeypatch.setattr(term_mod, "rag_search", _stub_rag_search)
    out = term_mod.lookup_terminology.invoke({"term": "SG"})
    assert out["matched_by"] == "exact_code"
    assert out["hits"][0]["metadata"]["source"] == "geography"


def test_semantic_search_fallback(monkeypatch):
    monkeypatch.setattr(term_mod, "rag_search", _stub_rag_search)
    out = term_mod.lookup_terminology.invoke({"term": "natural gas combined cycle"})
    assert out["matched_by"] == "semantic_search"
    assert len(out["hits"]) >= 1
    assert "PWRNGA" in out["summary"]


def test_chinese_query_works(monkeypatch):
    monkeypatch.setattr(term_mod, "rag_search", _stub_rag_search)
    out = term_mod.lookup_terminology.invoke({"term": "天然气发电"})
    assert out["matched_by"] == "semantic_search"
    assert out["hits"][0]["metadata"]["code"] == "PWRNGA"


def test_not_found(monkeypatch):
    monkeypatch.setattr(term_mod, "rag_search", _stub_rag_search)
    out = term_mod.lookup_terminology.invoke({"term": "unknown gibberish"})
    assert out["matched_by"] == "not_found"
    assert out["hits"] == []
