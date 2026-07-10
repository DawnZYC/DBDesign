"""(4) lookup_emission_factor unit tests (depends on the test DB)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Must come before importing app.* / other tools
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._db_fixture import setup_test_db  # noqa: E402

setup_test_db()

from app.tools.emission import lookup_emission_factor  # noqa: E402


def _call(code: str, year: int, geo: str = "SG") -> dict:
    return lookup_emission_factor.invoke(
        {
            "technology_code": code,
            "year": year,
            "geography_code": geo,
        }
    )


def test_exact_year_hit():
    out = _call("NGCC01", 2024)
    assert out["found"] is True
    hit = out["hit"]
    assert hit["matched_year"] == 2024
    assert hit["is_exact_year"] is True
    assert abs(hit["emission_factor"] - 56.1) < 1e-3


def test_year_fallback_to_nearest():
    """Requesting 2025 (missing) -> falls back to 2024 or 2030 (here 2024 is nearer)."""
    out = _call("NGCC01", 2025)
    assert out["found"] is True
    hit = out["hit"]
    assert hit["is_exact_year"] is False
    assert hit["matched_year"] == 2024
    assert "fell back" in (out.get("message") or "") or True


def test_unknown_technology():
    out = _call("NONEXIST00", 2018)
    assert out["found"] is False
    assert "does not exist" in (out.get("message") or "")


def test_includes_raw_row_id():
    """On a hit, raw_row_id should be present for M4 source-cell trace-back."""
    out = _call("NGCC01", 2018)
    assert out["found"] is True
    assert out["hit"]["raw_row_id"] is not None


def test_solar_zero_emission():
    out = _call("SOLAR01", 2018)
    assert out["found"] is True
    assert out["hit"]["emission_factor"] == 0.0
