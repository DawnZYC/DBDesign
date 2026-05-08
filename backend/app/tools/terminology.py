"""① lookup_terminology — 领域术语查询。

策略：
  1. 如果 term 看起来像 commodity_code（全大写字母 + 数字，长度 4-15），直接查 PG 字典
  2. 否则走 RAG 语义检索，从领域知识库召回 top-k
  3. 返回结构化 metadata + 自然语言摘要，方便 Agent 后续步骤使用
"""
from __future__ import annotations

import re
from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field
from sqlalchemy import select

from app import models
from app.database import SessionLocal
from app.rag import search as rag_search
from app.tools._base import with_observability

# 形如 SG / PWRNGA / WTEEEC / PWRRTFCO2 的代码（2-20 位大写字母 + 数字 + 可能含连字符）
# 短到 2 位以支持 geography 代码（SG, MY, US 等）
_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_-]{1,19}$")


class LookupTerminologyInput(BaseModel):
    term: str = Field(
        ...,
        description="待查询的术语（commodity 代码 / 行业名 / 自然语言描述）",
        min_length=1,
    )
    k: int = Field(default=5, ge=1, le=20, description="RAG 召回 top-k")


class TerminologyHit(BaseModel):
    text: str
    score: float
    metadata: dict[str, Any]


class TerminologyResponse(BaseModel):
    matched_by: str = Field(..., description="exact_code / semantic_search / not_found")
    hits: list[TerminologyHit]
    summary: str = Field(..., description="一句话摘要，给 Agent 拼上下文用")


@tool("lookup_terminology", args_schema=LookupTerminologyInput)
@with_observability("lookup_terminology")
def lookup_terminology(term: str, k: int = 5) -> dict:
    """Resolve a domain term to its canonical commodity / sector / definition.

    First tries exact code match against the commodity dictionary. If no exact hit,
    falls back to semantic search over the domain knowledge base (commodities, sectors,
    geographies, and the manual domain_knowledge.md).
    """
    term = term.strip()

    # 1) 精确 code 查询
    if _CODE_RE.match(term):
        hit = _exact_code_lookup(term)
        if hit:
            return TerminologyResponse(
                matched_by="exact_code",
                hits=[hit],
                summary=hit.text,
            ).model_dump()

    # 2) RAG 语义检索
    rag_hits = rag_search(term, k=k)
    if rag_hits:
        hits = [
            TerminologyHit(text=h.text, score=h.score, metadata=h.metadata)
            for h in rag_hits
        ]
        top = hits[0]
        return TerminologyResponse(
            matched_by="semantic_search",
            hits=hits,
            summary=f"最相关：{top.text[:120]}（score={top.score:.2f}）",
        ).model_dump()

    return TerminologyResponse(
        matched_by="not_found",
        hits=[],
        summary=f"未在知识库中找到 '{term}' 的相关条目。",
    ).model_dump()


def _exact_code_lookup(term: str) -> TerminologyHit | None:
    """走 PG 字典精确查 commodity / sector / geography 代码。"""
    db = SessionLocal()
    try:
        # commodity
        c = db.scalar(
            select(models.Commodity).where(models.Commodity.commodity_code == term)
        )
        if c:
            text_parts = [f"商品 {c.commodity_code}"]
            if c.commodity_description:
                text_parts.append(c.commodity_description)
            if c.commodity_set:
                text_parts.append(f"set={c.commodity_set}")
            if c.unit:
                text_parts.append(f"单位 {c.unit}")
            return TerminologyHit(
                text=" · ".join(text_parts),
                score=1.0,
                metadata={
                    "source": "commodity",
                    "code": c.commodity_code,
                    "set": c.commodity_set,
                    "unit": c.unit,
                    "description": c.commodity_description,
                },
            )
        # sector
        s = db.scalar(
            select(models.Sector).where(models.Sector.sector_code == term.upper())
        )
        if s:
            return TerminologyHit(
                text=f"行业 {s.sector_code}（{s.sector_name}）",
                score=1.0,
                metadata={"source": "sector", "code": s.sector_code, "name": s.sector_name},
            )
        # geography
        g = db.scalar(
            select(models.Geography).where(models.Geography.geography_code == term.upper())
        )
        if g:
            return TerminologyHit(
                text=f"地区 {g.geography_code}（{g.geography_name or '?'}）",
                score=1.0,
                metadata={"source": "geography", "code": g.geography_code},
            )
        return None
    finally:
        db.close()
