"""Tests for VT_SG_PWR converter.

Focuses on the pure lookup helpers and small slices of the end-to-end pipeline
that can be driven with hand-built DataFrames.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.converters.base_model import MISSING
from app.converters.models import vt_sg_pwr
from app.converters.models.vt_sg_pwr import VTSGPWRConverter


# ---------------------------------------------------------------------------
# Static helper
# ---------------------------------------------------------------------------
class TestPickCost:
    def test_exact_year(self):
        assert VTSGPWRConverter._pick_cost({2020: 100, 2030: 200}, 2020) == 100

    def test_falls_back_to_latest_prior(self):
        assert VTSGPWRConverter._pick_cost({2020: 100, 2030: 200}, 2025) == 100

    def test_skips_nan_for_exact_year(self):
        assert VTSGPWRConverter._pick_cost({2020: np.nan, 2018: 5}, 2020) == 5

    def test_no_prior_returns_missing(self):
        assert VTSGPWRConverter._pick_cost({2030: 99}, 2020) == MISSING

    def test_empty_dict(self):
        assert VTSGPWRConverter._pick_cost({}, 2020) == MISSING


# ---------------------------------------------------------------------------
# EF lookup
# ---------------------------------------------------------------------------
class TestGetEf:
    def setup_method(self):
        self.conv = VTSGPWRConverter("dummy.xlsx")
        self.conv._emi = {"PWRNGA": 50.0}
        self.conv._pwr_comm = {"FOO": "PWRNGA", "BAR": "PWRBAR"}

    def test_emi_override_wins(self):
        # PWRWASWTE00 maps via EF_OVERRIDES.
        assert self.conv._get_ef("PWRWASWTE00") == vt_sg_pwr.EF_OVERRIDES["PWRWASWTE00"]

    def test_solar_process_returns_zero(self):
        # Any process in SOLAR_PROCESSES gets EF = 0.
        any_solar = next(iter(vt_sg_pwr.SOLAR_PROCESSES))
        assert self.conv._get_ef(any_solar) == 0

    def test_emi_value_used_when_commodity_present(self):
        assert self.conv._get_ef("FOO") == 50.0

    def test_falls_back_to_ef_map(self):
        # PWRBAR isn't in self._emi but PWRNGA is in EF_MAP — use a code we know is in EF_MAP.
        self.conv._pwr_comm["NGABASED"] = "PWRNGA"
        self.conv._emi = {}  # ensure fallback to EF_MAP
        assert self.conv._get_ef("NGABASED") == vt_sg_pwr.EF_MAP["PWRNGA"]

    def test_unknown_returns_missing(self):
        assert self.conv._get_ef("UNKNOWN") == MISSING


# ---------------------------------------------------------------------------
# AFA conversion
# ---------------------------------------------------------------------------
class TestConvertAfa:
    def setup_method(self):
        self.conv = VTSGPWRConverter("dummy.xlsx")

    def test_nan_returns_missing(self):
        assert self.conv._convert_afa(np.nan) == MISSING

    def test_mapped_value(self):
        assert self.conv._convert_afa(0.75) == 0.8
        assert self.conv._convert_afa(0.14) == 0.1

    def test_unmapped_value_kept_as_is(self):
        assert self.conv._convert_afa(0.99) == 0.99


# ---------------------------------------------------------------------------
# Commodity lookup
# ---------------------------------------------------------------------------
class TestGetCommodity:
    def setup_method(self):
        self.conv = VTSGPWRConverter("dummy.xlsx")
        self.conv._pwr_comm = {"REGULAR": "PWRNGA"}

    def test_override_wins(self):
        # PWRWASWTE00 has explicit override = MISSING
        assert self.conv._get_commodity("PWRWASWTE00") == MISSING

    def test_pwr_comm_lookup(self):
        assert self.conv._get_commodity("REGULAR") == "PWRNGA"

    def test_unknown_returns_missing(self):
        assert self.conv._get_commodity("NEW_CODE") == MISSING


# ---------------------------------------------------------------------------
# Capacity rows
# ---------------------------------------------------------------------------
class TestGetCapacityRows:
    def setup_method(self):
        self.conv = VTSGPWRConverter("dummy.xlsx")
        self.conv._cap_year_headers = [2018, 2020, 2030]
        self.conv._data_by = {
            "REG": {
                "bound": "UP",
                "capacity": {2018: 100, 2020: 100, 2030: 200},
            },
            "FXCODE": {
                "bound": "FX",
                "capacity": {2018: 50, 2020: 60, 2030: 70},
            },
            "EMPTY": {
                "bound": "UP",
                "capacity": {2018: 0, 2020: np.nan, 2030: 0},
            },
        }
        self.conv._sol_data = {}

    def test_no_capacity_proc(self):
        assert self.conv._get_capacity_rows("PWRNGACCH11") == [(2018, MISSING)]

    def test_regular_dedups_consecutive_repeats(self):
        rows = self.conv._get_capacity_rows("REG")
        # 2018 and 2020 share the same value 100 so we only keep the first.
        assert rows == [(2018, 100), (2030, 200)]

    def test_fixed_bound_keeps_first_valid_only(self):
        rows = self.conv._get_capacity_rows("FXCODE")
        assert rows == [(2018, 50)]

    def test_empty_capacity_falls_back_to_missing(self):
        rows = self.conv._get_capacity_rows("EMPTY")
        assert rows == [(2018, MISSING)]

    def test_solar_uses_sol_data_years(self):
        # Pick any solar process to exercise the branch.
        proc = next(iter(vt_sg_pwr.SOLAR_PROCESSES))
        self.conv._sol_data[proc] = {"invcost": {2020: 100, 2030: 200}, "fixom": {}, "varom": {}}
        rows = self.conv._get_capacity_rows(proc)
        assert rows == [(2020, MISSING), (2030, MISSING)]

    def test_solar_with_no_invcost_defaults_to_2018(self):
        proc = next(iter(vt_sg_pwr.SOLAR_PROCESSES))
        self.conv._sol_data[proc] = {"invcost": {}, "fixom": {}, "varom": {}}
        rows = self.conv._get_capacity_rows(proc)
        assert rows == [(2018, MISSING)]


# ---------------------------------------------------------------------------
# parse_emi
# ---------------------------------------------------------------------------
class TestParseEmi:
    def test_extracts_commodity_ef_pairs(self):
        conv = VTSGPWRConverter("dummy.xlsx")
        # Row 4 holds commodity names from column 2 onwards, row 6 holds EF values.
        df = pd.DataFrame(
            [
                ["x"] * 5,
                ["x"] * 5,
                ["x"] * 5,
                ["x"] * 5,
                ["x", "x", "PWRNGA", "PWRCOA", "PWRBMS"],
                ["x"] * 5,
                ["x", "x", 56.1, 94.6, 0.0],
            ]
        )
        conv._sheets = {"EMI": df}
        conv._parse_emi()
        assert conv._emi == {"PWRNGA": 56.1, "PWRCOA": 94.6, "PWRBMS": 0.0}

    def test_skips_nan_values(self):
        conv = VTSGPWRConverter("dummy.xlsx")
        df = pd.DataFrame(
            [
                ["x"] * 4,
                ["x"] * 4,
                ["x"] * 4,
                ["x"] * 4,
                ["x", "x", "PWRNGA", "PWRMISSING"],
                ["x"] * 4,
                ["x", "x", 56.1, np.nan],
            ]
        )
        conv._sheets = {"EMI": df}
        conv._parse_emi()
        assert conv._emi == {"PWRNGA": 56.1}


# ---------------------------------------------------------------------------
# _parse_data_by
# ---------------------------------------------------------------------------
def _make_data_by_df(processes: list[dict]) -> pd.DataFrame:
    """Build a minimal Data_BY DataFrame matching the layout _parse_data_by expects.

    Column layout (0-indexed):
      0=active, 1=code, 2=desc, 3=heat_rate, 4=efficiency, 5=afa,
      6=lifetime, 7=bound,
      8-14=invcost values, 15-21=fixom values, 22-28=varom values,
      29+=capacity values.
    Row 0: unused header.
    Row 1: year labels for invcost(8-14), fixom(15-21), varom(22-28), cap(29+).
    Row 2+: process data.
    """
    n_cols = 31
    rows: list[list[object]] = []

    # Row 0 – unused
    rows.append([None] * n_cols)

    # Row 1 – year headers
    header: list[object] = [None] * n_cols
    header[8] = 2018.0  # invcost
    header[15] = 2018.0  # fixom
    header[22] = 2018.0  # varom
    header[29] = 2018.0  # cap year 1
    header[30] = 2020.0  # cap year 2
    rows.append(header)

    # Data rows
    for p in processes:
        row: list[object] = [None] * n_cols
        row[0] = p.get("active", 1)
        row[1] = p.get("code", "PROC")
        row[2] = p.get("desc", "desc")
        row[3] = p.get("heat_rate", 6.5)
        row[4] = p.get("efficiency", 0.55)
        row[5] = p.get("afa", 0.75)
        row[6] = p.get("lifetime", 25.0)
        row[7] = p.get("bound", "UP")
        row[8] = p.get("invcost", 1000.0)
        row[15] = p.get("fixom", 30.0)
        row[22] = p.get("varom", 5.0)
        row[29] = p.get("cap_2018", 500.0)
        row[30] = p.get("cap_2020", 600.0)
        rows.append(row)

    return pd.DataFrame(rows)


class TestParseDataBy:
    def test_parses_valid_process(self):
        conv = VTSGPWRConverter("dummy.xlsx")
        df = _make_data_by_df([{"code": "PWRNGACCF01", "bound": "FX"}])
        conv._sheets = {"Data_BY": df}
        conv._parse_data_by()

        assert "PWRNGACCF01" in conv._data_by
        assert conv._process_order == ["PWRNGACCF01"]
        assert conv._cap_year_headers == [2018, 2020]
        entry = conv._data_by["PWRNGACCF01"]
        assert entry["bound"] == "FX"
        assert entry["invcost"] == {2018: 1000.0}
        assert entry["capacity"] == {2018: 500.0, 2020: 600.0}

    def test_skips_inactive_row(self):
        conv = VTSGPWRConverter("dummy.xlsx")
        df = _make_data_by_df(
            [
                {"code": "ACTIVE", "active": 1},
                {"code": "INACTIVE", "active": 0},
            ]
        )
        conv._sheets = {"Data_BY": df}
        conv._parse_data_by()

        assert "ACTIVE" in conv._data_by
        assert "INACTIVE" not in conv._data_by

    def test_skips_reserved_codes(self):
        """Rows whose code is a sentinel string must be ignored."""
        conv = VTSGPWRConverter("dummy.xlsx")
        df = _make_data_by_df(
            [
                {"code": "*"},
                {"code": "Main Grid"},
                {"code": "Embeded or Autoproducer"},
                {"code": "Code"},
                {"code": "REAL_PROC"},
            ]
        )
        conv._sheets = {"Data_BY": df}
        conv._parse_data_by()

        assert list(conv._data_by.keys()) == ["REAL_PROC"]

    def test_skips_non_string_code(self):
        conv = VTSGPWRConverter("dummy.xlsx")
        df = _make_data_by_df([{"code": 42}, {"code": "OK_PROC"}])
        conv._sheets = {"Data_BY": df}
        conv._parse_data_by()

        assert list(conv._data_by.keys()) == ["OK_PROC"]


# ---------------------------------------------------------------------------
# _parse_pwr
# ---------------------------------------------------------------------------
def _make_pwr_df(entries: list[dict]) -> pd.DataFrame:
    """Minimal PWR sheet: 14 columns, data starts at row 6 (index 6).

    cols: 0..1=unused, 2=proc_code, 3..9=unused, 10=commodity, 11=unused,
          12=share0, 13=share.
    """
    n_cols = 14
    # 6 blank header rows
    rows: list[list[object]] = [[None] * n_cols for _ in range(6)]
    for e in entries:
        row: list[object] = [None] * n_cols
        row[2] = e.get("code")  # proc code (or None / sentinel)
        row[10] = e.get("comm")  # commodity
        row[12] = e.get("share0", 1)
        row[13] = e.get("share", 1)
        rows.append(row)
    return pd.DataFrame(rows)


class TestParsePwr:
    def test_extracts_commodity_for_process(self):
        conv = VTSGPWRConverter("dummy.xlsx")
        df = _make_pwr_df(
            [
                {"code": "PWRNGACCF01"},
                {"comm": "PWRNGA", "share0": 0.5, "share": 0.9},
            ]
        )
        conv._sheets = {"PWR": df}
        conv._parse_pwr()

        assert conv._pwr_comm["PWRNGACCF01"] == "PWRNGA"
        assert conv._pwr_share0["PWRNGACCF01"] == 0.5
        assert conv._pwr_share["PWRNGACCF01"] == 0.9

    def test_skips_sentinel_codes(self):
        conv = VTSGPWRConverter("dummy.xlsx")
        df = _make_pwr_df(
            [
                {"code": "*"},
                {"comm": "PWRNGA"},
                {"code": "Technology Name"},
                {"comm": "PWRCOA"},
                {"code": "REAL"},
                {"comm": "PWRHFO"},
            ]
        )
        conv._sheets = {"PWR": df}
        conv._parse_pwr()

        # Sentinel rows should not have set current_code → REAL gets PWRHFO
        assert "REAL" in conv._pwr_comm
        assert conv._pwr_comm["REAL"] == "PWRHFO"

    def test_only_first_commodity_row_per_process(self):
        """Second occurrence of same process code must not overwrite the first."""
        conv = VTSGPWRConverter("dummy.xlsx")
        df = _make_pwr_df(
            [
                {"code": "PROC"},
                {"comm": "FIRST"},
                {"comm": "SECOND"},
            ]
        )
        conv._sheets = {"PWR": df}
        conv._parse_pwr()

        assert conv._pwr_comm["PROC"] == "FIRST"

    def test_skips_star_commodity(self):
        conv = VTSGPWRConverter("dummy.xlsx")
        df = _make_pwr_df(
            [
                {"code": "PROC"},
                {"comm": "*"},
                {"comm": "REAL_COMM"},
            ]
        )
        conv._sheets = {"PWR": df}
        conv._parse_pwr()

        assert conv._pwr_comm.get("PROC") == "REAL_COMM"


# ---------------------------------------------------------------------------
# _parse_sol
# ---------------------------------------------------------------------------
def _make_sol_df(process_rows: list[dict], year: int = 2018) -> pd.DataFrame:
    """Minimal SOL sheet.

    Row 3 (index 3) holds headers; col 9 is proc code.
    We place one INVCOST, FIXOM, VAROM column (plus a uc_rhsrt col before INVCOST).
    """
    # We need at least 11 columns: 0-8 unused, 9=code, 10=uc_rhsrt, 11=invcost, 12=fixom, 13=varom
    n_cols = 14
    rows: list[list[object]] = [[None] * n_cols for _ in range(4)]

    # Row 3: headers
    header = [None] * n_cols
    header[11] = f"INVCOST~{year}"
    header[12] = f"FIXOM~{year}"
    header[13] = f"VAROM~{year}"
    rows[3] = header

    for p in process_rows:
        row: list[object] = [None] * n_cols
        row[9] = p.get("code")
        row[10] = p.get("uc_rhsrt", None)
        row[11] = p.get("invcost", None)
        row[12] = p.get("fixom", None)
        row[13] = p.get("varom", None)
        rows.append(row)

    return pd.DataFrame(rows)


class TestParseSol:
    def test_parses_first_occurrence_as_sol_data(self):
        conv = VTSGPWRConverter("dummy.xlsx")
        df = _make_sol_df([{"code": "PWRSOLLPV00", "invcost": 1000.0, "fixom": 10.0, "varom": 0.0}])
        conv._sheets = {"SOL": df}
        conv._parse_sol()

        assert "PWRSOLLPV00" in conv._sol_data
        assert conv._sol_data["PWRSOLLPV00"]["invcost"] == {2018: 1000.0}
        assert conv._sol_data["PWRSOLLPV00"]["fixom"] == {2018: 10.0}

    def test_parses_second_occurrence_as_uc_rhsrt(self):
        conv = VTSGPWRConverter("dummy.xlsx")
        df = _make_sol_df(
            [
                {"code": "PWRSOLLPV00", "invcost": 1000.0, "fixom": 10.0},
                {"code": "PWRSOLLPV00", "uc_rhsrt": 0.029},
            ]
        )
        conv._sheets = {"SOL": df}
        conv._parse_sol()

        assert "PWRSOLLPV00" in conv._sol_uc_rhsrt
        # The uc_rhsrt col sits one before the invcost col (col 10 vs col 11)
        assert 2018 in conv._sol_uc_rhsrt["PWRSOLLPV00"]

    def test_skips_non_string_codes(self):
        conv = VTSGPWRConverter("dummy.xlsx")
        df = _make_sol_df([{"code": None}, {"code": "REAL", "invcost": 500.0}])
        conv._sheets = {"SOL": df}
        conv._parse_sol()

        assert "REAL" in conv._sol_data
        assert None not in conv._sol_data

    def test_skips_sol_skip_codes(self):
        from app.converters.models.vt_sg_pwr import SOL_SKIP_CODES

        conv = VTSGPWRConverter("dummy.xlsx")
        skip_code = next(iter(SOL_SKIP_CODES))
        df = _make_sol_df([{"code": skip_code}, {"code": "KEPT", "invcost": 200.0}])
        conv._sheets = {"SOL": df}
        conv._parse_sol()

        assert skip_code not in conv._sol_data
        assert "KEPT" in conv._sol_data

    def test_invalid_year_header_skipped(self):
        """A header that looks like INVCOST~ but has a bad year is silently dropped."""
        conv = VTSGPWRConverter("dummy.xlsx")
        n_cols = 12
        rows: list[list[object]] = [[None] * n_cols for _ in range(4)]
        header = [None] * n_cols
        header[11] = "INVCOST~bad"
        rows[3] = header
        row = [None] * n_cols
        row[9] = "PROC"
        row[11] = 999.0
        rows.append(row)
        df = pd.DataFrame(rows)
        conv._sheets = {"SOL": df}
        conv._parse_sol()
        # The bad column produces None as the year; the dict still parses without crash.
        assert "PROC" in conv._sol_data


# ---------------------------------------------------------------------------
# _build_rows
# ---------------------------------------------------------------------------
def _make_converter_with_data(
    codes: list[str],
    *,
    include_solar: bool = False,
) -> VTSGPWRConverter:
    """Return a VTSGPWRConverter pre-populated for _build_rows unit tests."""
    conv = VTSGPWRConverter("dummy.xlsx")
    conv._cap_year_headers = [2018, 2020]
    conv._emi = {"PWRNGA": 56.1}
    conv._pwr_comm = {c: "PWRNGA" for c in codes if c not in vt_sg_pwr.SOLAR_PROCESSES}
    conv._sol_data = {}
    conv._data_by = {}

    for code in codes:
        if code in vt_sg_pwr.SOLAR_PROCESSES:
            conv._sol_data[code] = {
                "invcost": {2018: 900.0, 2020: 850.0},
                "fixom": {2018: 9.0},
                "varom": {},
            }
            conv._data_by[code] = {
                "description": "Solar",
                "heat_rate": np.nan,
                "efficiency": np.nan,
                "afa": 0.75,
                "lifetime": 30.0,
                "bound": "UP",
                "invcost": {},
                "fixom": {},
                "varom": {},
                "capacity": {2018: 0, 2020: 0},
            }
        else:
            conv._data_by[code] = {
                "description": "Gas CC",
                "heat_rate": 6.5,
                "efficiency": 0.55,
                "afa": 0.75,
                "lifetime": 25.0,
                "bound": "UP",
                "invcost": {2018: 1200.0, 2020: 1100.0},
                "fixom": {2018: 30.0},
                "varom": {2018: 5.0},
                "capacity": {2018: 500.0, 2020: 600.0},
            }
    return conv


class TestBuildRows:
    def test_regular_process_produces_records(self):
        conv = _make_converter_with_data(["PWRNGACCF01"])
        rows = conv._build_rows("PWRNGACCF01")

        assert len(rows) >= 1
        r = rows[0]
        assert r.process_code == "PWRNGACCF01"
        assert r.year == 2018
        assert r.ef == 56.1  # from conv._emi via _pwr_comm
        assert r.heat_rate == 6.5
        assert r.efficiency == 0.55
        assert r.variable_opex_unit == "PJ (2018)"

    def test_solar_process_produces_records(self):
        solar_code = "PWRSOLLPV00"
        conv = _make_converter_with_data([solar_code])
        rows = conv._build_rows(solar_code)

        assert len(rows) >= 1
        r = rows[0]
        assert r.process_code == solar_code
        assert r.ef == 0  # solar → EF = 0
        assert r.heat_rate == MISSING
        assert r.efficiency == MISSING
        assert r.variable_opex == MISSING

    def test_solar_variant_no_varom_unit(self):
        """SOLAR_VARIANTS in NO_VAROM_UNIT_PROCS must set var_unit=MISSING."""
        variant = "BDESOLLPV00"
        conv = _make_converter_with_data([variant])
        rows = conv._build_rows(variant)

        assert len(rows) >= 1
        assert rows[0].variable_opex_unit == MISSING

    def test_cogen_process_overrides_efficiency(self):
        """COGEN_ELEC_EFF processes must use the fixed efficiency map."""
        code = "IRFNGACGP00"
        conv = _make_converter_with_data([code])
        # Set raw efficiency to something different to confirm override wins.
        conv._data_by[code]["efficiency"] = 0.99
        rows = conv._build_rows(code)

        assert rows[0].efficiency == vt_sg_pwr.COGEN_ELEC_EFF[code]

    def test_no_capacity_proc_produces_missing_cap(self):
        """NO_CAPACITY_PROCS must result in capacity=MISSING."""
        code = "PWRNGACCH11"
        conv = _make_converter_with_data([code])
        rows = conv._build_rows(code)

        assert rows[0].capacity == MISSING

    def test_commodity_share_override(self):
        """Process in COMMODITY_SHARE_OVERRIDES must use that share value."""
        code = "PWRWASWTE00"
        conv = _make_converter_with_data([code])
        rows = conv._build_rows(code)

        assert rows[0].commodity_share == vt_sg_pwr.COMMODITY_SHARE_OVERRIDES[code]

    def test_lifetime_nan_becomes_missing(self):
        code = "PWRNGACCF01"
        conv = _make_converter_with_data([code])
        conv._data_by[code]["lifetime"] = np.nan
        rows = conv._build_rows(code)

        assert rows[0].lifetime == MISSING

    def test_uc_rhsrt_fixed_injected(self):
        """PWRSOLLPV00 has a UC_RHSRT_FIXED entry; first year's value must appear."""
        code = "PWRSOLLPV00"
        conv = _make_converter_with_data([code])
        rows = conv._build_rows(code)

        years_with_uc = [r for r in rows if r.uc_rhsrt != MISSING]
        assert len(years_with_uc) > 0
