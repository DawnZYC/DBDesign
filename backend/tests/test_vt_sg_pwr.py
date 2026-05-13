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
