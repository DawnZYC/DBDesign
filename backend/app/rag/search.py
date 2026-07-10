"""RAG retrieval interface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.rag.chroma_client import get_vectorstore


@dataclass
class SearchHit:
    """A single retrieval hit."""

    text: str
    score: float  # similarity (converted so that higher = more relevant)
    metadata: dict[str, Any]


def search(query: str, k: int = 5) -> list[SearchHit]:
    """Run similarity search over the global collection and return top-k.

    score meaning: 1 - distance (smaller distance = more similar -> higher score).
    """
    if not query.strip():
        return []
    vs = get_vectorstore()
    pairs = vs.similarity_search_with_score(query=query, k=k)
    hits: list[SearchHit] = []
    for doc, distance in pairs:
        # Chroma defaults to cosine distance (0 = identical, 2 = opposite)
        # Convert to score = 1 - distance / 2 to be more intuitive for the frontend
        score = max(0.0, min(1.0, 1.0 - float(distance) / 2.0))
        hits.append(
            SearchHit(
                text=doc.page_content,
                score=score,
                metadata=dict(doc.metadata or {}),
            )
        )
    return hits
