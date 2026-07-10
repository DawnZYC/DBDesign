"""RAG abstraction layer (M1).

Public API:
  - get_embedder(): embedding factory (LangChain Embeddings interface)
  - get_vectorstore(): ChromaDB persistent vector store
  - search(query, k): simple semantic retrieval interface
  - ingest_dictionary(db) / ingest_markdown(path): ingestion
"""

from app.rag.chroma_client import get_vectorstore, reset_collection
from app.rag.embeddings import (
    EMBEDDING_REGISTRY,
    EmbeddingProviderConfig,
    get_embedder,
    list_embedding_providers,
)
from app.rag.search import SearchHit, search

__all__ = [
    "EMBEDDING_REGISTRY",
    "EmbeddingProviderConfig",
    "SearchHit",
    "get_embedder",
    "get_vectorstore",
    "list_embedding_providers",
    "reset_collection",
    "search",
]
