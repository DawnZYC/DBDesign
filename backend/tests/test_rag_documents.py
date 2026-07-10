"""Knowledge-document upload management route tests (/api/rag/documents).

All vector-store operations are mocked; no dependency on chroma / embedding models.
"""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient


def _client() -> TestClient:
    from app.main import app

    return TestClient(app)


class TestUploadDocument:
    def test_upload_markdown_returns_chunks(self):
        with patch("app.routers.rag.ingest_uploaded_text", return_value=3) as ing:
            resp = _client().post(
                "/api/rag/documents",
                files={"file": ("notes.md", b"## A\nx\n\n## B\ny\n\n## C\nz", "text/markdown")},
            )
        assert resp.status_code == 201
        assert resp.json() == {"file": "notes.md", "chunks": 3}
        ing.assert_called_once()

    def test_rejects_wrong_suffix(self):
        resp = _client().post(
            "/api/rag/documents",
            files={"file": ("evil.exe", b"xx", "application/octet-stream")},
        )
        assert resp.status_code == 400

    def test_rejects_empty_file(self):
        resp = _client().post(
            "/api/rag/documents",
            files={"file": ("empty.md", b"   ", "text/markdown")},
        )
        assert resp.status_code == 400

    def test_rejects_non_utf8(self):
        resp = _client().post(
            "/api/rag/documents",
            files={"file": ("bin.md", b"\xff\xfe\x00\x01", "text/markdown")},
        )
        assert resp.status_code == 400


class TestListAndDelete:
    def test_list_documents(self):
        fake = [{"file": "a.md", "chunks": 2, "titles": ["T1", "T2"]}]
        with patch("app.routers.rag.list_uploaded_documents", return_value=fake):
            resp = _client().get("/api/rag/documents")
        assert resp.status_code == 200
        assert resp.json()[0]["file"] == "a.md"

    def test_delete_document(self):
        with patch("app.routers.rag.delete_uploaded_document", return_value=2):
            resp = _client().delete("/api/rag/documents/a.md")
        assert resp.status_code == 200
        assert resp.json() == {"file": "a.md", "deleted": 2}

    def test_delete_missing_returns_404(self):
        with patch("app.routers.rag.delete_uploaded_document", return_value=0):
            resp = _client().delete("/api/rag/documents/nope.md")
        assert resp.status_code == 404


class TestChunking:
    """ingest chunking logic (the pure-function part, no vector store)."""

    def test_h2_sections_preferred(self):
        from app.rag.ingest import _split_markdown_by_h2

        sections = _split_markdown_by_h2("## A\naaa\n\n## B\nbbb")
        assert [t for t, _ in sections] == ["A", "B"]

    def test_plain_text_fallback_chunks(self):
        from app.rag.ingest import _chunk_plain_text

        text = "\n\n".join(f"para {i} " + "x" * 300 for i in range(8))
        chunks = _chunk_plain_text(text)
        assert len(chunks) > 1
        assert all(body for _, body in chunks)
