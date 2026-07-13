"""RAG ingest / search / chroma_client unit tests — no real embeddings.

The vector store is replaced by a fake (in-memory) object, so these tests cover:
document builders (dictionary rows -> Documents), stable doc IDs, plain-text
chunking, upload ingest/list/delete round-trip, dictionary ingestion from the DB,
and the search score conversion.
"""

from __future__ import annotations

from unittest.mock import patch

from langchain_core.documents import Document

from app import models
from app.rag import ingest
from app.rag.chroma_client import get_collection_size
from app.rag.search import search


# -----------------------------------------------------------------------------
# Fake vector store (Chroma stand-in)
# -----------------------------------------------------------------------------
class FakeCollection:
    def __init__(self, store: dict):
        self._store = store

    def get(self, where=None, include=None):  # noqa: ANN001, ARG002
        def _match(md: dict) -> bool:
            if not where:
                return True
            conds = where.get("$and", [where])
            return all(md.get(k) == v for c in conds for k, v in c.items())

        ids = [i for i, (_, md) in self._store.items() if _match(md)]
        return {"ids": ids, "metadatas": [self._store[i][1] for i in ids]}

    def delete(self, ids):  # noqa: ANN001
        for i in ids:
            self._store.pop(i, None)

    def count(self):
        return len(self._store)


class FakeVectorStore:
    def __init__(self):
        self.store: dict[str, tuple[str, dict]] = {}
        self._collection = FakeCollection(self.store)
        self.search_result: list[tuple[Document, float]] = []

    def add_documents(self, documents, ids):  # noqa: ANN001
        for doc, id_ in zip(documents, ids, strict=True):
            self.store[id_] = (doc.page_content, dict(doc.metadata or {}))

    def similarity_search_with_score(self, query, k):  # noqa: ANN001, ARG002
        return self.search_result[:k]


# -----------------------------------------------------------------------------
# Document builders
# -----------------------------------------------------------------------------
def test_commodity_doc_filters_none_metadata():
    c = models.Commodity(commodity_code="COAL01", commodity_set="NRG", unit=None)
    doc = ingest._commodity_to_doc(c)
    assert "COAL01" in doc.page_content
    assert "Energy" in doc.page_content
    assert doc.metadata["source"] == "commodity"
    assert "unit" not in doc.metadata  # None filtered out


def test_sector_and_geography_docs():
    s = models.Sector(sector_code="POWER", sector_name="Power")
    g = models.Geography(geography_code="SG", geography_name=None)
    sd = ingest._sector_to_doc(s)
    gd = ingest._geography_to_doc(g)
    assert sd.metadata == {"source": "sector", "code": "POWER", "name": "Power"}
    assert "SG" in gd.page_content
    assert "name" not in gd.metadata


def test_make_doc_id_all_branches():
    mk = ingest._make_doc_id
    assert mk(Document(page_content="x", metadata={"source": "commodity", "code": "C1"})) == (
        "commodity::C1"
    )
    assert mk(
        Document(page_content="x", metadata={"source": "manual", "file": "f.md", "title": "T"})
    ) == ("manual::f.md::T")
    assert mk(
        Document(page_content="x", metadata={"source": "upload", "file": "u.md", "chunk": 2})
    ) == ("upload::u.md::2")
    fallback = mk(Document(page_content="x", metadata={"source": "other"}))
    assert fallback.startswith("other::")


# -----------------------------------------------------------------------------
# Plain-text chunking
# -----------------------------------------------------------------------------
def test_chunk_plain_text_aggregates_paragraphs():
    text = "\n\n".join(f"paragraph {i} " + "x" * 300 for i in range(8))
    chunks = ingest._chunk_plain_text(text)
    assert len(chunks) > 1
    assert all(title == "" for title, _ in chunks)
    joined = "".join(body for _, body in chunks)
    assert "paragraph 0" in joined and "paragraph 7" in joined


def test_chunk_plain_text_empty_returns_original():
    assert ingest._chunk_plain_text("just one line") == [("", "just one line")]


# -----------------------------------------------------------------------------
# Upload ingest / list / delete round-trip
# -----------------------------------------------------------------------------
def test_uploaded_doc_roundtrip():
    vs = FakeVectorStore()
    with patch("app.rag.ingest.get_vectorstore", return_value=vs):
        n = ingest.ingest_uploaded_text(
            "## Alpha\n\ncontent a\n\n## Beta\n\ncontent b", file_name="notes.md"
        )
        assert n == 2

        listed = ingest.list_uploaded_documents()
        assert listed == [{"file": "notes.md", "chunks": 2, "titles": ["Alpha", "Beta"]}]

        # Re-upload with fewer chunks -> old chunks must not survive
        n2 = ingest.ingest_uploaded_text("plain body only", file_name="notes.md")
        assert n2 == 1
        assert ingest.list_uploaded_documents()[0]["chunks"] == 1

        deleted = ingest.delete_uploaded_document("notes.md")
        assert deleted == 1
        assert ingest.list_uploaded_documents() == []


def test_ingest_uploaded_empty_text_is_noop():
    vs = FakeVectorStore()
    with patch("app.rag.ingest.get_vectorstore", return_value=vs):
        assert ingest.ingest_uploaded_text("   ", file_name="empty.md") == 0
    assert vs.store == {}


# -----------------------------------------------------------------------------
# Dictionary ingestion (real SQLite session, fake vector store)
# -----------------------------------------------------------------------------
def test_ingest_dictionary_counts(db_session):
    # Earlier suites (importer/schema-mapper e2e) replace tables on the shared engine
    # with simplified fixtures; rebuild the full ORM schema so dictionary writes work.
    from app.database import Base, engine

    db_session.rollback()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db_session.add(models.Sector(sector_code="POWER", sector_name="Power"))
    db_session.add(models.Geography(geography_code="SG", geography_name="Singapore"))
    db_session.add(models.Commodity(commodity_code="COAL01", commodity_set="NRG"))
    db_session.commit()

    vs = FakeVectorStore()
    with patch("app.rag.ingest.get_vectorstore", return_value=vs):
        counts = ingest.ingest_dictionary(db_session)

    assert counts["sector"] >= 1
    assert counts["geography"] >= 1
    assert counts["commodity"] >= 1
    assert "sector::POWER" in vs.store
    assert "commodity::COAL01" in vs.store


# -----------------------------------------------------------------------------
# search(): score conversion + empty-query guard
# -----------------------------------------------------------------------------
def test_search_converts_distance_to_score():
    # NB: app.rag re-exports a `search` *function* that shadows the module attribute,
    # so resolve the real module via sys.modules for patching.
    import sys

    search_mod = sys.modules["app.rag.search"]
    vs = FakeVectorStore()
    vs.search_result = [
        (Document(page_content="exact", metadata={"source": "manual"}), 0.0),
        (Document(page_content="far", metadata={}), 2.0),
    ]
    with patch.object(search_mod, "get_vectorstore", return_value=vs):
        hits = search("coal", k=5)
    assert hits[0].score == 1.0
    assert hits[1].score == 0.0
    assert hits[0].text == "exact"


def test_search_blank_query_returns_empty():
    assert search("   ") == []


# -----------------------------------------------------------------------------
# chroma_client.get_collection_size
# -----------------------------------------------------------------------------
def test_get_collection_size_uses_collection_count():
    vs = FakeVectorStore()
    vs.store["a"] = ("x", {})
    with patch("app.rag.chroma_client.get_vectorstore", return_value=vs):
        assert get_collection_size() == 1


def test_get_collection_size_swallows_errors():
    class Broken:
        @property
        def _collection(self):
            raise RuntimeError("chroma down")

    with patch("app.rag.chroma_client.get_vectorstore", return_value=Broken()):
        assert get_collection_size() == 0
