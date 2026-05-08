"""RAG 检索接口。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.rag.chroma_client import get_vectorstore


@dataclass
class SearchHit:
    """单条检索命中结果。"""

    text: str
    score: float          # 相似度（已转为「越大越相关」）
    metadata: dict[str, Any]


def search(query: str, k: int = 5) -> list[SearchHit]:
    """对全局 collection 做相似度检索，返回 top-k。

    score 语义：1 - distance（distance 越小越相似 → score 越大越相关）。
    """
    if not query.strip():
        return []
    vs = get_vectorstore()
    pairs = vs.similarity_search_with_score(query=query, k=k)
    hits: list[SearchHit] = []
    for doc, distance in pairs:
        # Chroma 默认走 cosine distance（0 = 完全相同，2 = 完全相反）
        # 这里转成 score = 1 - distance / 2 让前端更直观
        score = max(0.0, min(1.0, 1.0 - float(distance) / 2.0))
        hits.append(SearchHit(
            text=doc.page_content,
            score=score,
            metadata=dict(doc.metadata or {}),
        ))
    return hits
