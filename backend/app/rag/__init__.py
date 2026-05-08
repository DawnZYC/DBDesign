"""RAG 抽象层（M1）。

对外暴露：
  - get_embedder(): Embedding 工厂（LangChain Embeddings 接口）
  - get_vectorstore(): ChromaDB 持久化向量库
  - search(query, k): 简单语义检索接口
  - ingest_dictionary(db) / ingest_markdown(path): 灌库
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
