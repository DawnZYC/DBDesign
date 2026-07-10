"""(1) lookup_terminology unit tests (depends on DB; the RAG part uses a monkeypatch stub to avoid downloading a model)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._db_fixture import setup_test_db  # noqa: E402

setup_test_db()

from app.tools import terminology as term_mod  # noqa: E402

# CJK string "natural gas power" expressed as unicode escapes so the source stays
# English-only while still exercising the normalizer's CJK handling.
_CJK_NATURAL_GAS = "\u5929\u7136\u6c14"  # natural gas
_CJK_NATURAL_GAS_POWER = "\u5929\u7136\u6c14\u53d1\u7535"  # natural gas power generation


def _stub_rag_search(query: str, k: int = 5):
    """RAG stub: return a fixed 'semantic hit' based on the query."""
    from app.rag.search import SearchHit

    if _CJK_NATURAL_GAS in query or "natural gas" in query.lower():
        return [
            SearchHit(
                text="Commodity code: NGAS01 | Description: Natural gas for power",
                score=0.85,
                metadata={"source": "commodity", "code": "NGAS01"},
            )
        ]
    if "carbon" in query.lower() or "co2" in query.lower():
        return [
            SearchHit(
                text="Commodity code: CO2_01 | Description: Power-sector CO2",
                score=0.78,
                metadata={"source": "commodity", "code": "CO2_01"},
            )
        ]
    return []


def test_exact_code_lookup_commodity(monkeypatch):
    monkeypatch.setattr(term_mod, "rag_search", _stub_rag_search)
    out = term_mod.lookup_terminology.invoke({"term": "NGAS01"})
    assert out["matched_by"] == "exact_code"
    assert len(out["hits"]) == 1
    hit = out["hits"][0]
    assert hit["metadata"]["code"] == "NGAS01"
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
    assert "NGAS01" in out["summary"]


def test_cjk_query_works(monkeypatch):
    """A CJK query should still route through the semantic-search path (normalizer keeps CJK)."""
    monkeypatch.setattr(term_mod, "rag_search", _stub_rag_search)
    out = term_mod.lookup_terminology.invoke({"term": _CJK_NATURAL_GAS_POWER})
    assert out["matched_by"] == "semantic_search"
    assert out["hits"][0]["metadata"]["code"] == "NGAS01"


def test_not_found(monkeypatch):
    monkeypatch.setattr(term_mod, "rag_search", _stub_rag_search)
    out = term_mod.lookup_terminology.invoke({"term": "unknown gibberish"})
    assert out["matched_by"] == "not_found"
    assert out["hits"] == []
