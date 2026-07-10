"""(2) convert_unit — unit conversion.

Supports the units common in ESM / EcoTEA models:
  - Energy family (base PJ): PJ / ktoe / GWh / MWh / kWh / GJ
  - CO2 emission family (base kt-CO2): kt-CO2 / Mt-CO2 / t-CO2
  - Emission intensity (kt-CO2/PJ etc.) converts the energy and emission parts separately

Cross-family (e.g. PJ -> kt-CO2) is not allowed; it needs an emission factor, use lookup_emission_factor instead.
"""

from __future__ import annotations

import re
from typing import Literal

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.tools._base import with_observability

# -----------------------------------------------------------------------------
# Unit constants (multiplier from each unit -> the base)
# -----------------------------------------------------------------------------
# Energy units -> PJ
ENERGY_TO_PJ: dict[str, float] = {
    "PJ": 1.0,
    "ktoe": 1.0 / 23.885,  # 1 ktoe ≈ 0.041868 PJ
    "GWh": 0.0036,  # 1 GWh = 3.6 TJ = 0.0036 PJ
    "MWh": 3.6e-6,  # 1 MWh = 3.6 GJ = 3.6e-6 PJ
    "kWh": 3.6e-9,  # 1 kWh = 3.6 MJ = 3.6e-9 PJ
    "GJ": 1e-6,  # 1 GJ  = 1e-6 PJ
    "TJ": 1e-3,  # 1 TJ  = 1e-3 PJ
    "MJ": 1e-9,  # 1 MJ  = 1e-9 PJ
}

# CO2 emission units -> kt-CO2
CO2_TO_KT: dict[str, float] = {
    "kt-CO2": 1.0,
    "Mt-CO2": 1000.0,
    "t-CO2": 0.001,
    "Gt-CO2": 1_000_000.0,
    "kg-CO2": 1e-6,
}


def _normalize_unit_token(unit: str) -> str:
    """Tolerate variants like 'kt CO2' / 'kt-co₂' / 'kt CO_2'."""
    # Remove spaces, normalize hyphens, drop subscripts
    s = unit.strip()
    s = s.replace(" ", "").replace("_", "")
    s = s.replace("CO₂", "CO2").replace("co₂", "CO2").replace("co2", "CO2")
    # Casing: energy units capitalized, CO2 all caps
    return s


def _classify(unit: str) -> tuple[str, dict[str, float]] | None:
    """Identify which family the unit belongs to. Return (family name, that family's table) or None."""
    norm = _normalize_unit_token(unit)
    # Direct hit
    for table_name, table in (("energy", ENERGY_TO_PJ), ("co2", CO2_TO_KT)):
        for k in table:
            if norm.lower() == k.lower():
                return table_name, table
    # Handle the 't-CO2' style case
    if re.fullmatch(r"(?i)t[-_]?co2", norm):
        return "co2", CO2_TO_KT
    return None


# -----------------------------------------------------------------------------
# Input / output
# -----------------------------------------------------------------------------
class ConvertUnitInput(BaseModel):
    value: float = Field(..., description="Value to convert")
    from_unit: str = Field(..., description="Source unit, e.g. PJ / ktoe / GWh / kt-CO2")
    to_unit: str = Field(..., description="Target unit")


class ConvertUnitOutput(BaseModel):
    value: float
    from_unit: str
    to_unit: str
    family: Literal["energy", "co2"]
    factor: float = Field(..., description="The from->to multiplier, for auditing")


# -----------------------------------------------------------------------------
# Implementation
# -----------------------------------------------------------------------------
@tool("convert_unit", args_schema=ConvertUnitInput)
@with_observability("convert_unit")
def convert_unit(value: float, from_unit: str, to_unit: str) -> dict:
    """Convert a numeric value between energy or CO2 emission units.

    Energy family (base PJ): PJ, ktoe, GWh, MWh, kWh, GJ, TJ, MJ.
    CO2 family (base kt-CO2): kt-CO2, Mt-CO2, t-CO2, Gt-CO2, kg-CO2.
    Cross-family conversions are not supported; use emission factor instead.
    """
    src = _classify(from_unit)
    dst = _classify(to_unit)
    if src is None:
        raise ValueError(f"Unrecognized from_unit '{from_unit}'")
    if dst is None:
        raise ValueError(f"Unrecognized to_unit '{to_unit}'")
    if src[0] != dst[0]:
        raise ValueError(
            f"Cross-family conversion is not supported: {from_unit} ({src[0]}) -> {to_unit} ({dst[0]}); "
            f"for energy -> emission, use lookup_emission_factor"
        )

    table = src[1]
    # Find the actual key in the table (preserving casing)
    src_key = next(k for k in table if k.lower() == _normalize_unit_token(from_unit).lower())
    dst_key = next(k for k in table if k.lower() == _normalize_unit_token(to_unit).lower())

    factor = table[src_key] / table[dst_key]
    converted = value * factor

    return ConvertUnitOutput(
        value=converted,
        from_unit=src_key,
        to_unit=dst_key,
        family=src[0],
        factor=factor,
    ).model_dump()
