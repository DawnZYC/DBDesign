"""Converter for VT_SG_PRI_GREF -> EcoTEA Primary sheet.

Supports 39 processes:
  - 33 Import processes
  - 6  Mining processes

Each process expands to 27 rows (years 2018-2070, step 2).
"""

from __future__ import annotations

import contextlib

import numpy as np

from app.converters.base_model import MISSING, BaseConverter, PowerRecord

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TRACEABILITY = {
    "wp6_title": "Primary",
    "data_owner": "ESI",
    "data_provider": "WP1",
    "data_source": "GREF",
    "data_source_desc": "SG GREF v8.14; VT_SG_PRI_GREF",
    "data_user": "WP1",
    "usage_purpose": "Scenario analysis",
    "geography": "SG",
}

EF_FALLBACK = {
    "COA": 94.6,
    "PCK": 100.833,
    "NGA": 56.1,
    "LNG": 64.2,
    "HFO": 77.4,
    "BDS": 70.8,
    "DSL": 74.1,
    "GSL": 69.3,
    "BMS": 0,
    "URA": 0,
    "HYG": 0,
    "BEN": 43.079,
    "LPG": 63.1,
    "RGA": 57.567,
    "TGA": 55.733,
    "WAS": 50,
    "EEE": 0,
    "SOL": 0,
    "WAT": 0,
}

NO_EF_COMMS = {
    "OIL",
    "2MM",
    "3MM",
    "CFO",
    "NCH",
    "NCW",
    "NCC",
    "NCM",
    "NCI",
    "NCV",
    "NCT",
    "NCA",
    "NCF",
    "AGG",
    "WAG",
    "WSG",
    "LUF",
}

START_2071_PROCS = {"IMPHYG00", "IMPHYG01", "IMPHYG02", "IMPEEE01"}
ACT_BND_PROCS = {"IMPEEE00", "MINRGA00", "MINWAS00"}
CONSTRAINT_PROCS = {"IMPEEE00"}

# Header / placeholder rows that should be skipped while scanning sheets.
SKIP_TECH_NAMES = {"*", "TechName", "Technology Name"}

YEARS = list(range(2018, 2072, 2))


# ---------------------------------------------------------------------------
# Converter
# ---------------------------------------------------------------------------


class VTSGPRIConverter(BaseConverter):
    """Converter for VT_SG_PRI_GREF source files."""

    TARGET_SHEET = "Primary"

    def extract_power_records(self) -> list[PowerRecord]:
        self._load_sheets()
        self._parse_coef()
        self._processes: list[dict] = []
        self._parse_import()
        self._parse_mining()

        records: list[PowerRecord] = []
        for proc in self._processes:
            records.extend(self._build_rows(proc))
        return records

    # -- Sheet parsers -----------------------------------------------------

    def _parse_coef(self) -> None:
        df = self._sheets["Coef"]
        self._ef_by_comm: dict[str, float] = {}
        for i in range(len(df)):
            abbr = df.iloc[i, 1]
            ef = df.iloc[i, 2]
            if isinstance(abbr, str) and abbr.strip() and not abbr.startswith("*"):
                with contextlib.suppress(ValueError, TypeError):
                    self._ef_by_comm[abbr.strip()] = float(ef)

    @staticmethod
    def _find_col_maps(df) -> tuple[int | None, dict[int, int], dict[int, int]]:
        for i in range(min(15, len(df))):
            row = list(df.iloc[i])
            if not any(isinstance(v, str) and v.startswith("Cost~") for v in row):
                continue

            cost_cols: dict[int, int] = {}
            act_bnd_cols: dict[int, int] = {}

            for j, v in enumerate(row):
                if not isinstance(v, str):
                    continue
                if v.startswith("Cost~"):
                    try:
                        yr = int(v.split("~")[1])
                        cost_cols[yr] = j
                    except (IndexError, ValueError):
                        pass
                elif "ACT_BND" in v:
                    for part in v.split("~"):
                        try:
                            yr = int(part)
                            if 2000 <= yr <= 2100:
                                act_bnd_cols[yr] = j
                                break
                        except ValueError:
                            pass
            return i, cost_cols, act_bnd_cols

        return None, {}, {}

    def _parse_import(self) -> None:
        df = self._sheets["Import"]
        hdr_row, cost_cols, act_bnd_cols = self._find_col_maps(df)
        start_row = (hdr_row + 1) if hdr_row is not None else 6

        for i in range(start_row, len(df)):
            code = df.iloc[i, 2]
            if not isinstance(code, str):
                continue
            code = code.strip()
            if code in SKIP_TECH_NAMES or not code.upper().startswith("IMP"):
                continue

            desc = df.iloc[i, 3]
            comm_out = df.iloc[i, 10]
            start_v = df.iloc[i, 11]
            afa_v = df.iloc[i, 12]

            start_yr = 2071 if code in START_2071_PROCS else 2018
            if not isinstance(start_v, float) or not np.isnan(start_v):
                try:
                    candidate = int(float(start_v))
                    if candidate > 2000:
                        start_yr = candidate
                except (ValueError, TypeError):
                    pass

            self._processes.append(
                {
                    "sheet": "Import",
                    "code": code,
                    "description": str(desc).strip() if isinstance(desc, str) else str(desc),
                    "comm_out": comm_out.strip() if isinstance(comm_out, str) else MISSING,
                    "start_year": start_yr,
                    "afa": afa_v if not (isinstance(afa_v, float) and np.isnan(afa_v)) else MISSING,
                    "costs": self._read_year_vals(df, i, cost_cols),
                    "act_bnd": self._read_year_vals(df, i, act_bnd_cols),
                }
            )

    def _parse_mining(self) -> None:
        df = self._sheets["Mining"]
        hdr_row, cost_cols, act_bnd_cols = self._find_col_maps(df)
        start_row = (hdr_row + 1) if hdr_row is not None else 6

        for i in range(start_row, len(df)):
            code = df.iloc[i, 2]
            if not isinstance(code, str):
                continue
            code = code.strip()
            if code in SKIP_TECH_NAMES or not code.upper().startswith("MIN"):
                continue

            desc = df.iloc[i, 3]
            comm_out = df.iloc[i, 11]

            self._processes.append(
                {
                    "sheet": "Mining",
                    "code": code,
                    "description": str(desc).strip() if isinstance(desc, str) else str(desc),
                    "comm_out": comm_out.strip() if isinstance(comm_out, str) else MISSING,
                    "start_year": 2018,
                    "afa": MISSING,
                    "costs": self._read_year_vals(df, i, cost_cols),
                    "act_bnd": self._read_year_vals(df, i, act_bnd_cols),
                }
            )

    # -- Helpers -----------------------------------------------------------

    @staticmethod
    def _read_year_vals(df, row_idx: int, col_map: dict) -> dict:
        result: dict[int, object] = {}
        for yr, col in col_map.items():
            if col < len(df.columns):
                v = df.iloc[row_idx, col]
                if not (isinstance(v, float) and np.isnan(v)):
                    result[yr] = v
        return result

    @staticmethod
    def _pick_value(val_dict: dict, year: int) -> object:
        if year in val_dict:
            return val_dict[year]
        candidates = [(yr, v) for yr, v in val_dict.items() if yr <= year]
        if candidates:
            return max(candidates, key=lambda x: x[0])[1]
        return MISSING

    def _get_ef(self, comm_out: object) -> object:
        if not isinstance(comm_out, str) or comm_out == MISSING:
            return MISSING
        if comm_out in NO_EF_COMMS:
            return MISSING
        if comm_out in self._ef_by_comm:
            return self._ef_by_comm[comm_out]
        return EF_FALLBACK.get(comm_out, MISSING)

    # -- Row builder -------------------------------------------------------

    def _build_rows(self, proc: dict) -> list[PowerRecord]:
        code = proc["code"]
        comm_out = proc["comm_out"]
        ef = self._get_ef(comm_out)

        has_act_bnd = bool(proc["act_bnd"]) and code in ACT_BND_PROCS
        cap_type: object = "FX" if has_act_bnd else MISSING

        rows: list[PowerRecord] = []
        for year in YEARS:
            varom = self._pick_value(proc["costs"], year)

            if has_act_bnd:
                act_val = self._pick_value(proc["act_bnd"], year)
                cap_val: object = act_val
                constraint: object = act_val if code in CONSTRAINT_PROCS else MISSING
            else:
                cap_val = MISSING
                constraint = MISSING

            rows.append(
                PowerRecord(
                    **TRACEABILITY,
                    process_code=code,
                    description=proc["description"],
                    year=year,
                    start_year="NA",
                    lifetime=MISSING,
                    ef=ef,
                    ef_unit="PJ",
                    capex=MISSING,
                    fixed_opex="NA",
                    variable_opex=varom,
                    variable_opex_unit="GJ (2018)",
                    efficiency=MISSING,
                    commodity_share=1,
                    commodity=comm_out,
                    afa=proc["afa"],
                    heat_rate=MISSING,
                    capacity=cap_val,
                    capacity_type=cap_type,
                    constraint=constraint,
                )
            )
        return rows
