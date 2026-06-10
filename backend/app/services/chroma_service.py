"""ChromaDB service – initialise collection and index technology descriptions.

On startup the backend attempts to connect to ChromaDB and upsert any
technology_process rows that are not yet indexed.  This is done lazily so the
app still boots even if ChromaDB is temporarily unavailable.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import get_settings

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

COLLECTION_NAME = "ecotea_technologies"

_chroma_client: chromadb.HttpClient | None = None


def get_chroma_client() -> chromadb.HttpClient:
    """Return (and lazily create) the shared ChromaDB HTTP client."""
    global _chroma_client
    if _chroma_client is None:
        cfg = get_settings()
        _chroma_client = chromadb.HttpClient(
            host=cfg.chroma_host,
            port=cfg.chroma_port,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
    return _chroma_client


def get_or_create_collection() -> chromadb.Collection:
    client = get_chroma_client()
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def index_technologies(db_session: Session) -> int:
    """Upsert technology descriptions into ChromaDB.

    Returns the number of documents upserted.
    """
    from app.models import TechnologyProcess  # avoid circular import

    try:
        collection = get_or_create_collection()
    except Exception as exc:
        logger.warning("ChromaDB unavailable, skipping indexing: %s", exc)
        return 0

    rows = db_session.query(TechnologyProcess).all()
    if not rows:
        return 0

    documents: list[str] = []
    ids: list[str] = []
    metadatas: list[dict] = []

    for row in rows:
        doc_text = (
            f"{row.technology_code}: {row.technology_description or ''} "
            f"(sector_id={row.sector_id}, geography_id={row.geography_id})"
        ).strip()
        documents.append(doc_text)
        ids.append(str(row.technology_id))
        metadatas.append(
            {
                "technology_code": row.technology_code,
                "sector_id": row.sector_id,
                "geography_id": row.geography_id,
                "start_year": row.technology_start_year or 0,
                "grade": row.grade or "",
            }
        )

    # Upsert in batches of 200
    batch_size = 200
    total = 0
    for i in range(0, len(documents), batch_size):
        collection.upsert(
            documents=documents[i : i + batch_size],
            ids=ids[i : i + batch_size],
            metadatas=metadatas[i : i + batch_size],
        )
        total += len(documents[i : i + batch_size])

    logger.info("ChromaDB: upserted %d technology documents", total)
    return total


def semantic_search(query: str, n_results: int = 5) -> list[dict]:
    """Perform semantic search over technology descriptions.

    Returns a list of result dicts with keys: id, document, metadata, distance.
    """
    try:
        collection = get_or_create_collection()
        results = collection.query(
            query_texts=[query],
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )
    except Exception as exc:
        logger.warning("ChromaDB query failed: %s", exc)
        return []

    out: list[dict] = []
    ids = results.get("ids", [[]])[0]
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    dists = results.get("distances", [[]])[0]

    for tech_id, doc, meta, dist in zip(ids, docs, metas, dists):
        out.append(
            {
                "id": tech_id,
                "document": doc,
                "metadata": meta,
                "distance": round(dist, 4),
            }
        )
    return out
