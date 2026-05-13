"""Tests for VT_SG_PRI converter using fabricated DataFrames.

We don't need a real Excel file: BaseConverter._load_sheets is monkey-patched
to inject in-memory sheets, and then we exercise the converter's parsing /
row-building logic end to end.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.converters.base_model import MISSING
from app.converters.models import vt_sg_pri
from app.converters.models.vt_sg_pri import VTSGPRIConverter


# ---------------------------------------------------------------------------
# Static helper tests
# ---------------------------------------------------------------------------
class TestStaticHelpers:
    def test_find_col_maps_locates_cost_and_act_bnd(self):
        # Build a DataFrame whose row 3 holds the column header markers.
        rows = [
            ["filler"] * 12,
            ["filler"] * 12,
            ["filler"] * 12,
            [
                None,
                None,
                "TechName",
                "Description",
                "x",
                "x",
                "x",
                "x",
                "Cost~2020",
                "Cost~2030",
                "x",
                "ACT_BND~2025",
            ],
        ]
        df = pd.DataFrame(rows)
        hdr_row, cost_cols, act_bnd_cols = VTSGPRIConverter._find_col_maps(df)
        assert hdr_row == 3
        assert cost_cols == {2020: 8, 2030: 9}
        assert act_bnd_cols == {2025: 11}

    def test_find_col_maps_returns_none_when_missing(self):
        df = pd.DataFrame([["filler"] * 4 for _ in range(5)])
        assert VTSGPRIConverter._find_col_maps(df) == (None, {}, {})

    def test_read_year_vals_skips_nan_and_out_of_bounds(self):
        df = pd.DataFrame([[10, 20, 30, np.nan]])
        result = VTSGPRIConverter._read_year_vals(
            df, 0, {2020: 0, 2025: 2, 2030: 3, 2040: 99}
        )
        # NaN at 2030 is excluded; col 99 is out of bounds.
        assert result == {2020: 10, 2025: 30}

    def test_pick_value_exact_year(self):
        assert VTSGPRIConverter._pick_value({2020: "a", 2030: "b"}, 2020) == "a"

    def test_pick_value_falls_back_to_latest_earlier(self):
        # 2025 is not in the dict; the largest year <= 2025 wins.
        assert VTSGPRIConverter._pick_value({2020: "a", 2024: "b", 2030: "c"}, 2025) == "b"

    def test_pick_value_returns_missing_when_no_earlier(self):
        assert VTSGPRIConverter._pick_value({2030: "x"}, 2020) == MISSING

    def test_pick_value_empty_dict(self):
        assert VTSGPRIConverter._pick_value({}, 2025) == MISSING


# ---------------------------------------------------------------------------
# Emission factor lookup
# ---------------------------------------------------------------------------
class TestGetEf:
    def setup_method(self):
        self.conv = VTSGPRIConverter("dummy.xlsx")
        self.conv._ef_by_comm = {"NGA": 99.99}

    def test_explicit_ef(self):
        assert self.conv._get_ef("NGA") == 99.99

    def test_fallback_ef(self):
        # COA is not in _ef_by_comm but is in EF_FALLBACK.
        assert self.conv._get_ef("COA") == vt_sg_pri.EF_FALLBACK["COA"]

    def test_no_ef_commodity(self):
        # OIL is explicitly excluded.
        assert self.conv._get_ef("OIL") == MISSING

    def test_missing_input(self):
        assert self.conv._get_ef(MISSING) == MISSING
        assert self.conv._get_ef(None) == MISSING


# ---------------------------------------------------------------------------
# End-to-end extract_power_records with hand-built sheets
# ---------------------------------------------------------------------------
def _build_coef_sheet() -> pd.DataFrame:
    """Coef sheet: column 1 = abbreviation, column 2 = EF value."""
    rows = [
        ["header_row"] * 3,
        [None, "NGA", 55.5],
        [None, "*comment", 1],  # skipped (starts with *)
        [None, "BAD", "not_a_number"],  # skipped (ValueError)
    ]
    return pd.DataFrame(rows)


def _build_import_sheet() -> pd.DataFrame:
    # Header row at index 3.
    header = [
        None,
        None,
        "TechName",
        "Description",
        None,
        None,
        None,
        None,
        "Cost~2020",
        "Cost~2030",
        "CommOut",
        "Start",
        "AFA",
        "ACT_BND~2025",
    ]
    rows = [["x"] * len(header) for _ in range(3)]
    rows.append(header)
    # A real data row.
    rows.append(
        [
            None,
            None,
            "IMPNGA00",
            "Natural gas import",
            None,
            None,
            None,
            None,
            10.0,
            12.0,
            "NGA",
            2018.0,
            0.9,
            np.nan,
        ]
    )
    # A row that should be skipped (placeholder).
    rows.append([None, None, "*", None, None, None, None, None, np.nan, np.nan, None, np.nan, np.nan, np.nan])
    # Non-IMP prefix - skipped.
    rows.append(
        [
            None,
            None,
            "XYZ00",
            "ignored",
            None,
            None,
            None,
            None,
            1,
            2,
            "NGA",
            2018.0,
            0.9,
            np.nan,
        ]
    )
    return pd.DataFrame(rows)


def _build_mining_sheet() -> pd.DataFrame:
    header = [
        None,
        None,
        "TechName",
        "Description",
        None,
        None,
        None,
        None,
        "Cost~2020",
        "Cost~2030",
        None,
        "CommOut",
        "ACT_BND~2025",
    ]
    rows = [["x"] * len(header) for _ in range(3)]
    rows.append(header)
    rows.append(
        [
            None,
            None,
            "MINRGA00",
            "Mining RGA",
            None,
            None,
            None,
            None,
            5.0,
            6.0,
            None,
            "RGA",
            123.0,  # ACT_BND value at 2025
        ]
    )
    return pd.DataFrame(rows)


class TestExtractPowerRecords:
    def setup_method(self):
        self.conv = VTSGPRIConverter("dummy.xlsx")
        # Force the lazy loader to use our hand-built sheets.
        self.conv._sheets = {
            "Coef": _build_coef_sheet(),
            "Import": _build_import_sheet(),
            "Mining": _build_mining_sheet(),
        }
        # Avoid touching the filesystem.
        self.conv._load_sheets = lambda: None  # type: ignore[method-assign]

    def test_extracts_expected_record_count(self):
        records = self.conv.extract_power_records()
        # Two processes (IMP + MIN), each expanded to 27 years (2018-2070 step 2).
        assert len(records) == 27 * 2

    def test_record_has_traceability_fields(self):
        records = self.conv.extract_power_records()
        first = records[0]
        assert first.wp6_title == "Primary"
        assert first.data_owner == "ESI"
        assert first.geography == "SG"

    def test_import_process_emits_ef_from_coef(self):
        records = self.conv.extract_power_records()
        imp_rows = [r for r in records if r.process_code == "IMPNGA00"]
        assert len(imp_rows) == 27
        # EF was provided in the Coef sheet so should override the fallback.
        assert imp_rows[0].ef == 55.5

    def test_mining_act_bnd_drives_capacity(self):
        records = self.conv.extract_power_records()
        min_rows = [r for r in records if r.process_code == "MINRGA00"]
        # MINRGA00 is in ACT_BND_PROCS so capacity_type should be "FX".
        assert min_rows[0].capacity_type == "FX"
        # Capacity values pick up the 2025 act_bnd value 123 for years >= 2025.
        for row in min_rows:
            if row.year >= 2025:
                assert row.capacity == 123.0


# ---------------------------------------------------------------------------
# Parse_coef edge cases
# ---------------------------------------------------------------------------
class TestParseCoef:
    def test_invalid_ef_value_is_silently_dropped(self):
        conv = VTSGPRIConverter("dummy.xlsx")
        conv._sheets = {
            "Coef": pd.DataFrame(
                [
                    ["header"] * 3,
                    [None, "GOOD", 42.0],
                    [None, "BAD", "oops"],
                ]
            )
        }
        conv._parse_coef()
        assert conv._ef_by_comm == {"GOOD": 42.0}
