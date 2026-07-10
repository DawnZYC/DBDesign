"""M5 acceptance script — Schema-Mapping Agent column alignment.

Does three things, all with the deterministic backend (no API key, CI-runnable):
  1. Canonical template header -> headers_match_canonical() == True (fast path, no Agent)
  2. Deliberately renamed / shifted mock header -> map_columns() recovers the correct {source column -> canonical column}
  3. remap_cells() moves sample rows to canonical positions; values match the original canonical positions

Usage:
    cd backend && python scripts/verify_schema_mapping.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.agents import schema_mapper as sm  # noqa: E402

TEMPLATE = Path(__file__).parent.parent.parent / "uploads" / "template" / "EcoTEA Endo WP1.xlsx"

# Deliberate renames: replace canonical row-2 headers with synonyms (simulating a template version bump)
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
        print(f"Template not found: {TEMPLATE}")
        return 2

    wb = load_workbook(TEMPLATE, data_only=True, read_only=True)
    ws = wb["Power"]
    blobs = sm.extract_header_blobs(ws)
    row2 = sm.extract_primary_headers(ws)
    wb.close()

    passed = True

    # ---- 1) Canonical template takes the fast path ----
    print("[1] Canonical template header detection")
    passed &= _ok(sm.headers_match_canonical(blobs), "headers_match_canonical == True (fast path, no Agent)")

    # ---- 2) Build a renamed mock and verify mapping recovery ----
    print("[2] Renamed mock header -> column-alignment recovery")
    mock_blobs: dict[str, str] = {}
    expected_field: dict[str, str] = {}  # column -> expected standard field
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
        "after renaming, headers_match_canonical == False (triggers the slow path)",
    )

    mapping = sm.map_columns(mock_blobs, use_llm=False)
    got_field = {s.excel_column: s.target_field for s in mapping.suggestions}

    # Focus on verifying the renamed columns
    renamed_cols = [c for c, h in row2.items() if h.lower() in RENAME and c in expected_field]
    hit = sum(1 for c in renamed_cols if got_field.get(c) == expected_field[c])
    passed &= _ok(
        hit == len(renamed_cols),
        f"renamed columns recovered {hit}/{len(renamed_cols)}: " +
        ", ".join(f"{c}->{got_field.get(c)}" for c in renamed_cols),
    )

    # Overall accuracy
    total = len(expected_field)
    all_hit = sum(1 for c, f in expected_field.items() if got_field.get(c) == f)
    passed &= _ok(all_hit / total >= 0.9, f"overall column-match accuracy {all_hit}/{total} = {all_hit/total:.0%} (threshold 90%)")

    # ---- 3) remap_cells relocation correctness ----
    print("[3] remap_cells relocation")
    # Simulate an "unfamiliar file": put canonical-column values in rows at the same positions but with renamed headers.
    # Here we rename without shifting, so remap should be identity (source col == canonical col); values are unchanged after relocation.
    remap, review = sm.build_remap(mapping)
    sample = {col: f"val_{col}" for col in mock_blobs}
    remapped = sm.remap_cells(sample, remap)
    capex_spec = sm.FIELD_BY_NAME["capex"]
    capex_src = next((c for c, f in got_field.items() if f == "capex"), None)
    passed &= _ok(
        capex_src is not None and remapped.get(capex_spec.column) == f"val_{capex_src}",
        f"capex value relocated to canonical column {capex_spec.column} (source column {capex_src})",
    )
    passed &= _ok(len(remap) >= len(renamed_cols), f"build_remap auto-applied {len(remap)} columns, {len(review)} to review")

    print()
    print("=" * 48)
    print("✅ M5 acceptance passed" if passed else "❌ M5 acceptance has failures")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
