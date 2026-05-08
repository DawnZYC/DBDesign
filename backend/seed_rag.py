"""把 PG 字典 + 领域知识手册灌入 ChromaDB。

幂等：相同 ID 的文档会被 upsert，不会重复。
切换 embedding provider 后请先用 --reset 清掉 collection，因为向量维度不同。

用法：
  python seed_rag.py                     # 灌库（PG 字典 + domain_knowledge.md）
  python seed_rag.py --reset             # 清空 collection 后灌库
  python seed_rag.py --skip-md           # 只灌 PG 字典
  python seed_rag.py --md-file other.md  # 用别的 markdown 替代
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# 让 app 包可被 import
sys.path.insert(0, str(Path(__file__).parent))

from app.database import SessionLocal
from app.rag.chroma_client import (
    get_collection_size,
    get_vectorstore,
    reset_collection,
)
from app.rag.ingest import ingest_dictionary, ingest_markdown


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed RAG knowledge base")
    parser.add_argument("--reset", action="store_true",
                        help="先清空 collection 再灌（切 embedding provider 时用）")
    parser.add_argument("--skip-md", action="store_true",
                        help="跳过 markdown 灌入")
    parser.add_argument("--md-file", default="domain_knowledge.md",
                        help="markdown 文件路径（默认 domain_knowledge.md）")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    if args.reset:
        print(">>> Resetting collection ...")
        reset_collection()

    # 触发 vectorstore 初始化（首次会下载 embedding 模型）
    print(">>> Initializing vectorstore (首次会下载 embedding 模型) ...")
    get_vectorstore()
    print(f"    collection 当前文档数 = {get_collection_size()}")

    # 1) PG 字典
    print("\n>>> Ingesting PG dictionary (sector / geography / commodity) ...")
    db = SessionLocal()
    try:
        counts = ingest_dictionary(db)
        for k, v in counts.items():
            print(f"    {k:<10} {v:>4}")
    finally:
        db.close()

    # 2) Markdown
    if not args.skip_md:
        md_path = Path(args.md_file)
        if not md_path.is_absolute():
            md_path = Path(__file__).parent / md_path
        if md_path.exists():
            print(f"\n>>> Ingesting markdown {md_path.name} ...")
            n = ingest_markdown(md_path)
            print(f"    sections {n}")
        else:
            print(f"\n>>> WARN: markdown 不存在: {md_path}")

    print(f"\n>>> Done. collection 现在 {get_collection_size()} 条文档。")


if __name__ == "__main__":
    main()
