"""把 PG 字典 + 手工领域知识 灌入 ChromaDB。

支持两个数据源：
  - PG 三张字典表（commodity / sector / geography）→ 每行一个 Document
  - Markdown 文件（domain_knowledge.md）→ 按 H2 切段，每段一个 Document

每个 Document 的 metadata 里都带 source 字段（'commodity' / 'sector' / ...），
方便检索时过滤和回查。
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
# 字典 → Document
# -----------------------------------------------------------------------------
def _commodity_to_doc(c: models.Commodity) -> Document:
    """把 commodity 一行拼成富文本 + 结构化 metadata。"""
    parts: list[str] = []
    parts.append(f"商品代码: {c.commodity_code}")
    if c.commodity_description:
        parts.append(f"描述: {c.commodity_description}")
    if c.commodity_set:
        parts.append(f"集合(Csets): {c.commodity_set} ({'能源' if c.commodity_set == 'NRG' else '排放' if c.commodity_set == 'ENV' else '其他'})")
    if c.unit:
        parts.append(f"单位: {c.unit}")
    if c.lim_type:
        parts.append(f"约束类型(LimType): {c.lim_type}")
    if c.cts_lvl:
        parts.append(f"时间片层级(CTSLvl): {c.cts_lvl}")
    if c.peak_ts:
        parts.append(f"峰值时间片(PeakTS): {c.peak_ts}")
    if c.ctype:
        parts.append(f"商品类型(Ctype): {c.ctype}")
    text = " | ".join(parts)

    metadata: dict[str, str | None] = {
        "source": "commodity",
        "code": c.commodity_code,
        "set": c.commodity_set,
        "unit": c.unit,
        "description": c.commodity_description,
    }
    # Chroma 不支持 None metadata 值，过滤掉
    metadata = {k: v for k, v in metadata.items() if v is not None}
    return Document(page_content=text, metadata=metadata)


def _sector_to_doc(s: models.Sector) -> Document:
    text = f"行业(Sector): {s.sector_name}（代码 {s.sector_code}）"
    return Document(
        page_content=text,
        metadata={"source": "sector", "code": s.sector_code, "name": s.sector_name},
    )


def _geography_to_doc(g: models.Geography) -> Document:
    name = g.geography_name or g.geography_code
    text = f"地区(Geography): {name}（代码 {g.geography_code}）"
    md: dict[str, str] = {"source": "geography", "code": g.geography_code}
    if g.geography_name:
        md["name"] = g.geography_name
    return Document(page_content=text, metadata=md)


# -----------------------------------------------------------------------------
# Markdown 切段
# -----------------------------------------------------------------------------
_H2_RE = re.compile(r"^##\s+(.+?)\s*$", flags=re.MULTILINE)


def _split_markdown_by_h2(md: str) -> list[tuple[str, str]]:
    """按 ## 标题切段，返回 [(title, content), ...]。

    标题 # 一级被丢弃；H2 之前的内容（前言）与第一个 H2 合并。
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
# 公开 API
# -----------------------------------------------------------------------------
def ingest_dictionary(db: Session) -> dict[str, int]:
    """从 PG 读 sector / geography / commodity 全量灌入向量库。返回各类型条数。"""
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
    """灌入一个 markdown 文件（按 H2 分段）。返回段数。"""
    docs = _markdown_to_docs(path)
    if not docs:
        return 0
    ids = [_make_doc_id(d) for d in docs]
    vs = get_vectorstore()
    vs.add_documents(documents=docs, ids=ids)
    logger.info("Ingested markdown %s: %d sections", path.name, len(docs))
    return len(docs)


def _make_doc_id(doc: Document) -> str:
    """构造稳定的 ID（重复灌库时 upsert 而非新增）。

    格式：
      commodity::PWRCOA
      sector::POWER
      geography::SG
      manual::filename::title
    """
    md = doc.metadata or {}
    source = md.get("source", "unknown")
    if source in {"commodity", "sector", "geography"}:
        return f"{source}::{md.get('code', '')}"
    if source == "manual":
        return f"manual::{md.get('file', '')}::{md.get('title', '')}"
    # 兜底：用内容的 hash
    import hashlib
    h = hashlib.sha1(doc.page_content.encode("utf-8")).hexdigest()[:12]
    return f"{source}::{h}"
