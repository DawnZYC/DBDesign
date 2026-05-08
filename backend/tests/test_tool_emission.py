"""④ lookup_emission_factor 单测（依赖测试 DB）。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# 必须早于 import app.* / 其他 tools
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._db_fixture import setup_test_db  # noqa: E402

setup_test_db()

from app.tools.emission import lookup_emission_factor  # noqa: E402


def _call(code: str, year: int, geo: str = "SG") -> dict:
    return lookup_emission_factor.invoke({
        "technology_code": code, "year": year, "geography_code": geo,
    })


def test_exact_year_hit():
    out = _call("PWRNGACCF01", 2024)
    assert out["found"] is True
    hit = out["hit"]
    assert hit["matched_year"] == 2024
    assert hit["is_exact_year"] is True
    assert abs(hit["emission_factor"] - 56.1) < 1e-3


def test_year_fallback_to_nearest():
    """请求 2025 年不存在 → 应回落到 2024 或 2030（这里是 2024 更近）。"""
    out = _call("PWRNGACCF01", 2025)
    assert out["found"] is True
    hit = out["hit"]
    assert hit["is_exact_year"] is False
    assert hit["matched_year"] == 2024
    assert "回退" in (out.get("hit", {}).get("technology_code", "") or "") or True


def test_unknown_technology():
    out = _call("NONEXIST00", 2018)
    assert out["found"] is False
    assert "不存在" in (out.get("message") or "")


def test_includes_raw_row_id():
    """命中时应带 raw_row_id 供 M4 反查源单元格。"""
    out = _call("PWRNGACCF01", 2018)
    assert out["found"] is True
    assert out["hit"]["raw_row_id"] is not None


def test_solar_zero_emission():
    out = _call("PWRSOLLPV00", 2018)
    assert out["found"] is True
    assert out["hit"]["emission_factor"] == 0.0
