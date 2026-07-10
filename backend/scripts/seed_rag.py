"""Ingest the PG dictionaries + the domain knowledge manual into ChromaDB.

Idempotent: documents with the same ID are upserted, not duplicated.
After switching embedding provider, run --reset first to clear the collection (vector dims differ).

Usage (run from the backend/ directory):
  python scripts/seed_rag.py                     # ingest (PG dictionaries + data/domain_knowledge.md)
  python scripts/seed_rag.py --reset             # clear the collection then ingest
  python scripts/seed_rag.py --skip-md           # ingest only the PG dictionaries
  python scripts/seed_rag.py --md-file other.md  # use a different markdown file under data/
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Make the app package importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import SessionLocal
from app.rag.chroma_client import (
    get_collection_size,
    get_vectorstore,
    reset_collection,
)
from app.rag.ingest import ingest_dictionary, ingest_markdown


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed RAG knowledge base")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Clear the collection before ingesting (use when switching embedding provider)",
    )
    parser.add_argument("--skip-md", action="store_true", help="Skip markdown ingestion")
    parser.add_argument(
        "--md-file",
        default="domain_knowledge.md",
        help="Markdown file name under backend/data/ (or an absolute path); default domain_knowledge.md",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    if args.reset:
        print(">>> Resetting collection ...")
        reset_collection()

    # Trigger vectorstore initialization (first run downloads the embedding model)
    print(">>> Initializing vectorstore (first run downloads the embedding model) ...")
    get_vectorstore()
    print(f"    current collection doc count = {get_collection_size()}")

    # 1) PG dictionaries
    print("\n>>> Ingesting PG dictionary (sector / geography / commodity) ...")
    db = SessionLocal()
    try:
        counts = ingest_dictionary(db)
        for k, v in counts.items():
            print(f"    {k:<10} {v:>4}")
    finally:
        db.close()

    # 2) Markdown (RAG source content lives in backend/data/). The real domain_knowledge.md is
    #    confidential / gitignored; fall back to the sanitized .example.md so a fresh clone still
    #    seeds something.
    if not args.skip_md:
        md_path = Path(args.md_file)
        if not md_path.is_absolute():
            md_path = Path(__file__).parent.parent / "data" / md_path
        if not md_path.exists():
            example = md_path.with_suffix(".example.md")
            if example.exists():
                print(f"\n>>> {md_path.name} not found; using sanitized {example.name}")
                md_path = example
        if md_path.exists():
            print(f"\n>>> Ingesting markdown {md_path.name} ...")
            n = ingest_markdown(md_path)
            print(f"    sections {n}")
        else:
            print(f"\n>>> WARN: markdown not found: {md_path}")

    print(f"\n>>> Done. collection now has {get_collection_size()} documents.")


if __name__ == "__main__":
    main()
