"""验证 RAG 端到端：跑一组金标问题，输出 recall@1 / recall@3 / 平均 score。

使用前提：
  - PG 已经有数据（至少跑过一次 seed_commodities + import + seed_rag）
  - .env 里 EMBEDDING_PROVIDER 已配置

用法：
  python verify_rag.py                    # 用当前 embedding 跑全部金标
  python verify_rag.py --provider qwen   # 临时切到 qwen embedding（需先 reset）
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# 金标：自然语言问题 → 期望命中的文档 metadata.code（top-K 中含即算命中）
GOLDEN_QUESTIONS: list[dict] = [
    # 商品检索
    {"q": "natural gas for power generation", "expected_code": "PWRNGA"},
    {"q": "天然气发电用",                      "expected_code": "PWRNGA"},
    {"q": "biomass fuel",                     "expected_code": "PWRBMS"},
    {"q": "carbon capture and storage",        "expected_code": "PWRCO2C"},
    {"q": "incineration electricity",          "expected_code": "WTEEEC"},
    {"q": "solar power commodity",             "expected_code": "PWRSOL"},
    {"q": "煤炭发电",                          "expected_code": "PWRCOA"},
    {"q": "hydrogen energy",                   "expected_code": "PWRHYD"},
    {"q": "uranium for nuclear",               "expected_code": "PWRURA"},
    {"q": "retrofitted plant emission",        "expected_code": "PWRRTFCO2"},

    # 行业检索
    {"q": "data center sector",                "expected_code": "INFOCOMM"},
    {"q": "agriculture sector",                "expected_code": "AGRI"},
    {"q": "household residential",             "expected_code": "HOUSEHOLD"},

    # 知识手册段落（按段标题命中即可，没有特定 code）
    {"q": "PJ to ktoe conversion",             "expected_text_keyword": "PJ"},
    {"q": "kt-CO2 单位",                       "expected_text_keyword": "kt-CO"},
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", help="临时覆盖 embedding provider")
    parser.add_argument("--k", type=int, default=3)
    args = parser.parse_args()

    if args.provider:
        os.environ["EMBEDDING_PROVIDER"] = args.provider

    from app.config import get_settings
    get_settings.cache_clear()

    from app.rag import search

    settings = get_settings()
    print(f"\n>>> embedding provider = {settings.embedding_provider}")
    print(f">>> chroma persist dir  = {settings.chroma_persist_dir}")
    print(f">>> golden questions    = {len(GOLDEN_QUESTIONS)}")
    print(f">>> top-k                = {args.k}\n")

    hit_at_1 = 0
    hit_at_k = 0
    scores: list[float] = []

    for i, item in enumerate(GOLDEN_QUESTIONS, 1):
        q = item["q"]
        hits = search(q, k=args.k)
        if not hits:
            print(f"  [{i:>2}] {q!r:<45} → ∅ (no hits)")
            continue

        # 判定命中
        hit_codes = [h.metadata.get("code") for h in hits]
        hit_texts = [h.text for h in hits]
        first_score = hits[0].score
        scores.append(first_score)

        if "expected_code" in item:
            target = item["expected_code"]
            in_top1 = hit_codes[:1] and hit_codes[0] == target
            in_topk = target in hit_codes
        else:
            kw = item["expected_text_keyword"]
            in_top1 = kw.lower() in hit_texts[0].lower()
            in_topk = any(kw.lower() in t.lower() for t in hit_texts)

        if in_top1: hit_at_1 += 1
        if in_topk: hit_at_k += 1

        marker = "✓" if in_topk else "✗"
        print(
            f"  [{i:>2}] {marker} {q!r:<45} "
            f"→ top1={hit_codes[0] or '-':<14} score={first_score:.3f}"
        )

    n = len(GOLDEN_QUESTIONS)
    print()
    print(f"  recall@1  = {hit_at_1}/{n} = {hit_at_1/n:.0%}")
    print(f"  recall@{args.k}  = {hit_at_k}/{n} = {hit_at_k/n:.0%}")
    if scores:
        print(f"  avg top-1 score = {sum(scores)/len(scores):.3f}")
    print()


if __name__ == "__main__":
    main()
