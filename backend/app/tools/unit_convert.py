"""② convert_unit — 单位换算。

支持 SG-TIMES / EcoTEA 模型常用单位：
  - 能源族（PJ 为基准）：PJ / ktoe / GWh / MWh / kWh / GJ
  - CO₂ 排放族（kt-CO₂ 为基准）：kt-CO2 / Mt-CO2 / t-CO2
  - 排放强度（kt-CO₂/PJ 等）走能源 + 排放分别换算

跨族（譬如 PJ → kt-CO2）不允许，需用排放因子，请改用 lookup_emission_factor。
"""
from __future__ import annotations

import re
from typing import Literal

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.tools._base import with_observability

# -----------------------------------------------------------------------------
# 单位常数（各单位 → 基准的乘数）
# -----------------------------------------------------------------------------
# 能源单位 → PJ
ENERGY_TO_PJ: dict[str, float] = {
    "PJ": 1.0,
    "ktoe": 1.0 / 23.885,        # 1 ktoe ≈ 0.041868 PJ
    "GWh": 0.0036,                # 1 GWh = 3.6 TJ = 0.0036 PJ
    "MWh": 3.6e-6,                # 1 MWh = 3.6 GJ = 3.6e-6 PJ
    "kWh": 3.6e-9,                # 1 kWh = 3.6 MJ = 3.6e-9 PJ
    "GJ":  1e-6,                  # 1 GJ  = 1e-6 PJ
    "TJ":  1e-3,                  # 1 TJ  = 1e-3 PJ
    "MJ":  1e-9,                  # 1 MJ  = 1e-9 PJ
}

# CO₂ 排放单位 → kt-CO2
CO2_TO_KT: dict[str, float] = {
    "kt-CO2": 1.0,
    "Mt-CO2": 1000.0,
    "t-CO2":  0.001,
    "Gt-CO2": 1_000_000.0,
    "kg-CO2": 1e-6,
}


def _normalize_unit_token(unit: str) -> str:
    """容忍 'kt CO2' / 'kt-co₂' / 'kt CO_2' 等变体。"""
    # 去空格、统一连字符、去下标
    s = unit.strip()
    s = s.replace(" ", "").replace("_", "")
    s = s.replace("CO₂", "CO2").replace("co₂", "CO2").replace("co2", "CO2")
    # 大小写：能源单位首字母大写、CO2 全大写
    return s


def _classify(unit: str) -> tuple[str, dict[str, float]] | None:
    """识别 unit 属于哪一族。返回 (族名, 该族的换算表) 或 None。"""
    norm = _normalize_unit_token(unit)
    # 直接命中
    for table_name, table in (("energy", ENERGY_TO_PJ), ("co2", CO2_TO_KT)):
        for k in table:
            if norm.lower() == k.lower():
                return table_name, table
    # 兼容 't-CO2' 类的 case
    if re.fullmatch(r"(?i)t[-_]?co2", norm):
        return "co2", CO2_TO_KT
    return None


# -----------------------------------------------------------------------------
# 入参 / 出参
# -----------------------------------------------------------------------------
class ConvertUnitInput(BaseModel):
    value: float = Field(..., description="待换算的数值")
    from_unit: str = Field(..., description="原单位，如 PJ / ktoe / GWh / kt-CO2")
    to_unit: str = Field(..., description="目标单位")


class ConvertUnitOutput(BaseModel):
    value: float
    from_unit: str
    to_unit: str
    family: Literal["energy", "co2"]
    factor: float = Field(..., description="from→to 的乘数，便于审计")


# -----------------------------------------------------------------------------
# 实现
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
        raise ValueError(f"未识别的 from_unit '{from_unit}'")
    if dst is None:
        raise ValueError(f"未识别的 to_unit '{to_unit}'")
    if src[0] != dst[0]:
        raise ValueError(
            f"跨族换算不被支持：{from_unit}（{src[0]}）→ {to_unit}（{dst[0]}）；"
            f"如需能源 → 排放，请用 lookup_emission_factor"
        )

    table = src[1]
    # 找出表里实际的 key（保留大小写）
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
