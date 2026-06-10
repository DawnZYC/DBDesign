"""M5 验收脚本 — Schema-Mapping Agent 列对齐。

做三件事，全部用确定性后端（无需 API key，CI 可跑）：
  1. 标准模板表头 → headers_match_canonical() == True（走快路径，不调 Agent）
  2. 故意改名 / 换位的 mock 表头 → map_columns() 恢复出正确的「陌生列→标准列」
  3. remap_cells() 把样例行搬到标准列位后，值与原始标准列位一致

用法：
    cd backend && python verify_schema_mapping.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from openpyxl import Workbook, load_workbook

sys.path.insert(0, str(Path(__file__).parent))

from app.agents import schema_mapper as sm  # noqa: E402

TEMPLATE = Path(__file__).parent.parent / "uploads" / "template" / "EcoTEA Endo WP1.xlsx"

# 故意改名：把标准 row2 表头换成同义词（模拟 SG-TIMES 版本迭代）
RENAME = {
    "data owner": "owner of data",
    "capex": "build cost",
    "fixed opex": "FO&M charge",
    "variable opex": "VO&M",
    "ef": "emissions factor",
    "technology/process": "asset name",
    "year of data": "year",
}


def _ok(cond: bool, msg: str) -> bool:
    print(("  ✅ " if cond else "  ❌ ") + msg)
    return cond


def main() -> int:
    if not TEMPLATE.exists():
        print(f"找不到模板：{TEMPLATE}")
        return 2

    wb = load_workbook(TEMPLATE, data_only=True, read_only=True)
    ws = wb["Power"]
    blobs = sm.extract_header_blobs(ws)
    row2 = sm.extract_primary_headers(ws)
    wb.close()

    passed = True

    # ---- 1) 标准模板走快路径 ----
    print("[1] 标准模板表头判定")
    passed &= _ok(sm.headers_match_canonical(blobs), "headers_match_canonical == True（快路径，不调 Agent）")

    # ---- 2) 构造改名 mock，验证恢复映射 ----
    print("[2] 改名 mock 表头 → 列对齐恢复")
    mock_blobs: dict[str, str] = {}
    expected_field: dict[str, str] = {}  # 列 -> 期望标准字段
    for col, header in row2.items():
        spec = sm.FIELD_BY_COLUMN.get(col)
        if spec is None:
            continue
        low = header.lower()
        new_header = RENAME.get(low, header)
        mock_blobs[col] = new_header
        expected_field[col] = spec.field

    passed &= _ok(
        not sm.headers_match_canonical(mock_blobs),
        "改名后 headers_match_canonical == False（触发慢路径）",
    )

    mapping = sm.map_columns(mock_blobs, use_llm=False)
    got_field = {s.excel_column: s.target_field for s in mapping.suggestions}

    # 重点验证被改名的那些列
    renamed_cols = [c for c, h in row2.items() if h.lower() in RENAME and c in expected_field]
    hit = sum(1 for c in renamed_cols if got_field.get(c) == expected_field[c])
    passed &= _ok(
        hit == len(renamed_cols),
        f"改名列恢复 {hit}/{len(renamed_cols)}：" +
        ", ".join(f"{c}->{got_field.get(c)}" for c in renamed_cols),
    )

    # 整体准确率
    total = len(expected_field)
    all_hit = sum(1 for c, f in expected_field.items() if got_field.get(c) == f)
    passed &= _ok(all_hit / total >= 0.9, f"整体列匹配准确率 {all_hit}/{total} = {all_hit/total:.0%}（阈值 90%）")

    # ---- 3) remap_cells 搬运正确性 ----
    print("[3] remap_cells 搬运")
    # 模拟一个“陌生文件”：把标准列的值放在【相同列位但表头改名】的行里。
    # 这里改名不换位，所以 remap 应是 identity（陌生列==标准列），搬运后值不变。
    remap, review = sm.build_remap(mapping)
    sample = {col: f"val_{col}" for col in mock_blobs}
    remapped = sm.remap_cells(sample, remap)
    capex_spec = sm.FIELD_BY_NAME["capex"]
    capex_src = next((c for c, f in got_field.items() if f == "capex"), None)
    passed &= _ok(
        capex_src is not None and remapped.get(capex_spec.column) == f"val_{capex_src}",
        f"capex 值搬到标准列 {capex_spec.column}（源列 {capex_src}）",
    )
    passed &= _ok(len(remap) >= len(renamed_cols), f"build_remap 自动应用 {len(remap)} 列，待复核 {len(review)} 列")

    print()
    print("=" * 48)
    print("✅ M5 验收通过" if passed else "❌ M5 验收存在失败项")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
