"""ChromaDB persistent vector store wrapper.

Strategy:
  - PersistentClient: local embedded, directory controlled by settings.chroma_persist_dir
  - Singleton vectorstore, auto-injected with the current embedding provider
  - Switching embedding provider makes the old collection's dimension mismatch — reset_collection() clears it in one call
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from langchain_chroma import Chroma

from app.config import get_settings
from app.rag.embeddings import get_embedder

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_vectorstore() -> Chroma:
    """Get (or create) the persistent vectorstore singleton.

    The first call triggers loading the embedding model (the HuggingFace local model ~80MB, downloaded on first use).
    """
    settings = get_settings()
    persist_dir = Path(settings.chroma_persist_dir).expanduser().resolve()
    persist_dir.mkdir(parents=True, exist_ok=True)

    embedder = get_embedder()

    logger.info(
        "Init Chroma vectorstore: dir=%s collection=%s embedder=%s",
        persist_dir,
        settings.chroma_collection_name,
        type(embedder).__name__,
    )

    return Chroma(
        collection_name=settings.chroma_collection_name,
        embedding_function=embedder,
        persist_directory=str(persist_dir),
    )


def reset_collection() -> None:
    """Delete and recreate the collection (use after switching embedding provider)."""
    settings = get_settings()
    persist_dir = Path(settings.chroma_persist_dir).expanduser().resolve()

    # Clear the singleton cache
    get_vectorstore.cache_clear()

    if persist_dir.exists():
        # Deleting the collection via the chromadb client API is safer
        try:
            import chromadb

            client = chromadb.PersistentClient(path=str(persist_dir))
            try:
                client.delete_collection(name=settings.chroma_collection_name)
                logger.info(
                    "Deleted existing Chroma collection: %s", settings.chroma_collection_name
                )
            except Exception:  # noqa: BLE001
                logger.info("No existing collection to delete (ok)")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to delete via API (%s); falling back", exc)


def get_collection_size() -> int:
    """Return the number of documents in the current collection."""
    vs = get_vectorstore()
    try:
        return vs._collection.count()
    except Exception:  # noqa: BLE001
        return 0
