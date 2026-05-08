"""RAG 检索路由（M1）。"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.rag import list_embedding_providers, search
from app.rag.chroma_client import get_collection_size

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/rag", tags=["rag"])


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="自然语言查询")
    k: int = Field(default=5, ge=1, le=50)


class SearchResultItem(BaseModel):
    text: str
    score: float
    metadata: dict


class SearchResponse(BaseModel):
    query: str
    k: int
    hits: list[SearchResultItem]


@router.post("/search", response_model=SearchResponse, summary="语义检索领域知识库")
def rag_search(req: SearchRequest) -> SearchResponse:
    try:
        hits = search(req.query, k=req.k)
    except Exception as exc:  # noqa: BLE001
        logger.exception("RAG 检索失败")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"检索失败：{exc!s}",
        ) from exc
    return SearchResponse(
        query=req.query,
        k=req.k,
        hits=[
            SearchResultItem(text=h.text, score=h.score, metadata=h.metadata)
            for h in hits
        ],
    )


@router.get("/info", summary="RAG 子系统状态（向量库大小 + embedding provider）")
def rag_info() -> dict:
    """前端 settings 页可用：知道库里有多少条、当前 embedding 是哪个。"""
    try:
        size = get_collection_size()
    except Exception as exc:  # noqa: BLE001
        size = -1
        logger.warning("get_collection_size failed: %s", exc)

    return {
        "collection_size": size,
        "providers": list_embedding_providers(),
    }
