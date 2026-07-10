"""(1) lookup_terminology — domain terminology lookup.

Strategy:
  1. If `term` looks like a commodity_code (uppercase letters + digits, length 4-15), query the PG dictionary directly.
  2. Otherwise do RAG semantic retrieval, returning top-k from the domain knowledge base.
  3. Return structured metadata + a natural-language summary for use in later Agent steps.
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

# Codes like SG / NGCC01 / WTE01 (2-20 uppercase letters + digits + optional hyphen)
# Down to 2 chars to support geography codes (SG, MY, US, ...)
_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_-]{1,19}$")


class LookupTerminologyInput(BaseModel):
    term: str = Field(
        ...,
        description="Term to look up (commodity code / sector name / natural-language description)",
        min_length=1,
    )
    k: int = Field(default=5, ge=1, le=20, description="RAG top-k to retrieve")


class TerminologyHit(BaseModel):
    text: str
    score: float
    metadata: dict[str, Any]


class TerminologyResponse(BaseModel):
    matched_by: str = Field(..., description="exact_code / semantic_search / not_found")
    hits: list[TerminologyHit]
    summary: str = Field(..., description="One-line summary for the Agent to build context")


@tool("lookup_terminology", args_schema=LookupTerminologyInput)
@with_observability("lookup_terminology")
def lookup_terminology(term: str, k: int = 5) -> dict:
    """Resolve a domain term to its canonical commodity / sector / definition.

    First tries exact code match against the commodity dictionary. If no exact hit,
    falls back to semantic search over the domain knowledge base (commodities, sectors,
    geographies, and the manual domain_knowledge.md).
    """
    term = term.strip()

    # 1) Exact code lookup
    if _CODE_RE.match(term):
        hit = _exact_code_lookup(term)
        if hit:
            return TerminologyResponse(
                matched_by="exact_code",
                hits=[hit],
                summary=hit.text,
            ).model_dump()

    # 2) RAG semantic retrieval
    rag_hits = rag_search(term, k=k)
    if rag_hits:
        hits = [TerminologyHit(text=h.text, score=h.score, metadata=h.metadata) for h in rag_hits]
        top = hits[0]
        return TerminologyResponse(
            matched_by="semantic_search",
            hits=hits,
            summary=f"Most relevant: {top.text[:120]} (score={top.score:.2f})",
        ).model_dump()

    return TerminologyResponse(
        matched_by="not_found",
        hits=[],
        summary=f"No related entry found for '{term}' in the knowledge base.",
    ).model_dump()


def _exact_code_lookup(term: str) -> TerminologyHit | None:
    """Exact lookup of commodity / sector / geography codes via the PG dictionary."""
    db = SessionLocal()
    try:
        # commodity
        c = db.scalar(select(models.Commodity).where(models.Commodity.commodity_code == term))
        if c:
            text_parts = [f"Commodity {c.commodity_code}"]
            if c.commodity_description:
                text_parts.append(c.commodity_description)
            if c.commodity_set:
                text_parts.append(f"set={c.commodity_set}")
            if c.unit:
                text_parts.append(f"unit {c.unit}")
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
        s = db.scalar(select(models.Sector).where(models.Sector.sector_code == term.upper()))
        if s:
            return TerminologyHit(
                text=f"Sector {s.sector_code} ({s.sector_name})",
                score=1.0,
                metadata={"source": "sector", "code": s.sector_code, "name": s.sector_name},
            )
        # geography
        g = db.scalar(
            select(models.Geography).where(models.Geography.geography_code == term.upper())
        )
        if g:
            return TerminologyHit(
                text=f"Region {g.geography_code} ({g.geography_name or '?'})",
                score=1.0,
                metadata={"source": "geography", "code": g.geography_code},
            )
        return None
    finally:
        db.close()
