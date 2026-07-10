"""Ingest the PG dictionaries + manual domain knowledge into ChromaDB.

Two data sources are supported:
  - The three PG dictionary tables (commodity / sector / geography) -> one Document per row
  - A Markdown file (domain_knowledge.md) -> split by H2, one Document per section

Every Document's metadata carries a `source` field ('commodity' / 'sector' / ...),
for filtering and trace-back during retrieval.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from langchain_core.documents import Document
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.rag.chroma_client import get_vectorstore

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Dictionary -> Document
# -----------------------------------------------------------------------------
def _commodity_to_doc(c: models.Commodity) -> Document:
    """Assemble one commodity row into rich text + structured metadata."""
    parts: list[str] = []
    parts.append(f"Commodity code: {c.commodity_code}")
    if c.commodity_description:
        parts.append(f"Description: {c.commodity_description}")
    if c.commodity_set:
        kind = (
            "Energy"
            if c.commodity_set == "NRG"
            else "Emission"
            if c.commodity_set == "ENV"
            else "Other"
        )
        parts.append(f"Set (Csets): {c.commodity_set} ({kind})")
    if c.unit:
        parts.append(f"Unit: {c.unit}")
    if c.lim_type:
        parts.append(f"Constraint type (LimType): {c.lim_type}")
    if c.cts_lvl:
        parts.append(f"Timeslice level (CTSLvl): {c.cts_lvl}")
    if c.peak_ts:
        parts.append(f"Peak timeslice (PeakTS): {c.peak_ts}")
    if c.ctype:
        parts.append(f"Commodity type (Ctype): {c.ctype}")
    text = " | ".join(parts)

    metadata: dict[str, str | None] = {
        "source": "commodity",
        "code": c.commodity_code,
        "set": c.commodity_set,
        "unit": c.unit,
        "description": c.commodity_description,
    }
    # Chroma does not allow None metadata values; filter them out
    metadata = {k: v for k, v in metadata.items() if v is not None}
    return Document(page_content=text, metadata=metadata)


def _sector_to_doc(s: models.Sector) -> Document:
    text = f"Sector: {s.sector_name} (code {s.sector_code})"
    return Document(
        page_content=text,
        metadata={"source": "sector", "code": s.sector_code, "name": s.sector_name},
    )


def _geography_to_doc(g: models.Geography) -> Document:
    name = g.geography_name or g.geography_code
    text = f"Geography: {name} (code {g.geography_code})"
    md: dict[str, str] = {"source": "geography", "code": g.geography_code}
    if g.geography_name:
        md["name"] = g.geography_name
    return Document(page_content=text, metadata=md)


# -----------------------------------------------------------------------------
# Markdown splitting
# -----------------------------------------------------------------------------
_H2_RE = re.compile(r"^##\s+(.+?)\s*$", flags=re.MULTILINE)


def _split_markdown_by_h2(md: str) -> list[tuple[str, str]]:
    """Split by ## headings, returning [(title, content), ...].

    The top-level # heading is discarded; content before the first H2 (the preamble) is
    merged into the first H2.
    """
    matches = list(_H2_RE.finditer(md))
    if not matches:
        return [("", md.strip())]

    sections: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        title = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(md)
        content = md[start:end].strip()
        if content:
            sections.append((title, content))
    return sections


def _markdown_to_docs(path: Path) -> list[Document]:
    text = path.read_text(encoding="utf-8")
    sections = _split_markdown_by_h2(text)
    return [
        Document(
            page_content=f"## {title}\n\n{content}" if title else content,
            metadata={
                "source": "manual",
                "file": path.name,
                "title": title,
            },
        )
        for title, content in sections
    ]


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------
def ingest_dictionary(db: Session) -> dict[str, int]:
    """Read all of sector / geography / commodity from PG and ingest into the vector store. Returns per-type counts."""
    docs: list[Document] = []
    counts = {"sector": 0, "geography": 0, "commodity": 0}

    for s in db.scalars(select(models.Sector).order_by(models.Sector.sector_id)).all():
        docs.append(_sector_to_doc(s))
        counts["sector"] += 1

    for g in db.scalars(select(models.Geography).order_by(models.Geography.geography_id)).all():
        docs.append(_geography_to_doc(g))
        counts["geography"] += 1

    for c in db.scalars(select(models.Commodity).order_by(models.Commodity.commodity_id)).all():
        docs.append(_commodity_to_doc(c))
        counts["commodity"] += 1

    if docs:
        ids = [_make_doc_id(d) for d in docs]
        vs = get_vectorstore()
        vs.add_documents(documents=docs, ids=ids)
        logger.info("Ingested %d dict docs: %s", len(docs), counts)

    return counts


def ingest_markdown(path: Path) -> int:
    """Ingest one markdown file (split by H2). Returns the number of sections."""
    docs = _markdown_to_docs(path)
    if not docs:
        return 0
    ids = [_make_doc_id(d) for d in docs]
    vs = get_vectorstore()
    vs.add_documents(documents=docs, ids=ids)
    logger.info("Ingested markdown %s: %d sections", path.name, len(docs))
    return len(docs)


def _make_doc_id(doc: Document) -> str:
    """Build a stable ID (so re-ingestion upserts instead of duplicating).

    Format:
      commodity::COAL01
      sector::POWER
      geography::SG
      manual::filename::title
      upload::filename::chunk_index
    """
    md = doc.metadata or {}
    source = md.get("source", "unknown")
    if source in {"commodity", "sector", "geography"}:
        return f"{source}::{md.get('code', '')}"
    if source == "manual":
        return f"manual::{md.get('file', '')}::{md.get('title', '')}"
    if source == "upload":
        return f"upload::{md.get('file', '')}::{md.get('chunk', 0)}"
    # Fallback: hash of the content
    import hashlib

    h = hashlib.sha1(doc.page_content.encode("utf-8"), usedforsecurity=False).hexdigest()[:12]
    return f"{source}::{h}"


# -----------------------------------------------------------------------------
# Uploaded knowledge docs (source='upload', independent of manual/dictionary)
# -----------------------------------------------------------------------------
_FALLBACK_CHUNK_CHARS = 1200  # plain text without H2 headings is aggregated to this length


def _chunk_plain_text(text: str) -> list[tuple[str, str]]:
    """Fallback chunking for text without H2 structure: split by blank lines, aggregate to ~_FALLBACK_CHUNK_CHARS."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    buf = ""
    for p in paragraphs:
        if buf and len(buf) + len(p) > _FALLBACK_CHUNK_CHARS:
            chunks.append(buf)
            buf = p
        else:
            buf = f"{buf}\n\n{p}" if buf else p
    if buf:
        chunks.append(buf)
    return [("", c) for c in chunks] or [("", text.strip())]


def ingest_uploaded_text(content: str, *, file_name: str) -> int:
    """Ingest a user-uploaded markdown / plain-text knowledge doc. Returns the number of chunks.

    Prefers chunking by H2 headings (same rule as domain_knowledge.md); without H2, aggregates
    by paragraph. Re-uploading the same file name = overwrite (delete old chunks first, then write,
    so stale chunks don't remain when a new version has fewer chunks).
    """
    content = content.strip()
    if not content:
        return 0

    sections = _split_markdown_by_h2(content)
    if len(sections) == 1 and not sections[0][0]:
        sections = _chunk_plain_text(content)

    docs = [
        Document(
            page_content=f"## {title}\n\n{body}" if title else body,
            metadata={"source": "upload", "file": file_name, "title": title, "chunk": i},
        )
        for i, (title, body) in enumerate(sections)
    ]
    delete_uploaded_document(file_name)  # overwrite semantics
    ids = [_make_doc_id(d) for d in docs]
    vs = get_vectorstore()
    vs.add_documents(documents=docs, ids=ids)
    logger.info("Ingested uploaded doc %s: %d chunks", file_name, len(docs))
    return len(docs)


def list_uploaded_documents() -> list[dict]:
    """List all uploaded docs: [{file, chunks, titles}]."""
    vs = get_vectorstore()
    got = vs._collection.get(where={"source": "upload"}, include=["metadatas"])  # noqa: SLF001
    files: dict[str, dict] = {}
    for md in got.get("metadatas") or []:
        name = (md or {}).get("file", "unknown")
        entry = files.setdefault(name, {"file": name, "chunks": 0, "titles": []})
        entry["chunks"] += 1
        title = (md or {}).get("title")
        if title and title not in entry["titles"]:
            entry["titles"].append(title)
    return sorted(files.values(), key=lambda x: x["file"])


def delete_uploaded_document(file_name: str) -> int:
    """Delete all chunks of an uploaded doc. Returns the number deleted."""
    vs = get_vectorstore()
    got = vs._collection.get(  # noqa: SLF001
        where={"$and": [{"source": "upload"}, {"file": file_name}]},
        include=[],
    )
    ids = got.get("ids") or []
    if ids:
        vs._collection.delete(ids=ids)  # noqa: SLF001
        logger.info("Deleted uploaded doc %s: %d chunks", file_name, len(ids))
    return len(ids)
