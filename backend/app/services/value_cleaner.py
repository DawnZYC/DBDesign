"""单元格值清洗规则。

清洗 3 类规则（与 ER 图 v2 设计一致）：
  1. 占位符（'-' / 'NA' / '' / 空白） → SQL NULL
  2. 公式错误（#VALUE! 等） → 主表 NULL，但单独写 data_quality_issue
  3. 带语义混合文本（'COP: 3.91'） → 拆出 value / text / unit
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# -------------------------------------------------------------------------
# 常量
# -------------------------------------------------------------------------
PLACEHOLDER_LITERALS: frozenset[str] = frozenset(
    {"", "-", "—", "na", "n/a", "n.a.", "null", "none"}
)

EXCEL_ERROR_TOKENS: frozenset[str] = frozenset(
    {"#VALUE!", "#REF!", "#DIV/0!", "#N/A", "#NAME?", "#NULL!", "#NUM!"}
)

# A 列文本 → sector_code 的模糊映射（容忍同义词、复数）
SECTOR_NAME_TO_CODE: dict[str, str] = {
    "power": "POWER",
    "industry": "INDUSTRY",
    "industries": "INDUSTRY",
    "primary": "PRIMARY",
    "transport": "TRANSPORT",
    "transportation": "TRANSPORT",
    "water": "WATER",
    "waste": "WASTE",
    "building": "BUILDING",
    "buildings": "BUILDING",
    "household": "HOUSEHOLD",
    "households": "HOUSEHOLD",
    "agri": "AGRI",
    "agriculture": "AGRI",
    "agricultural": "AGRI",
    "infocomm": "INFOCOMM",
    "info comm": "INFOCOMM",
    "ict": "INFOCOMM",
}


# -------------------------------------------------------------------------
# 判定函数
# -------------------------------------------------------------------------
def is_placeholder(value: Any) -> bool:
    """是否为占位符（应转 NULL，不留痕）。"""
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in PLACEHOLDER_LITERALS
    return False


def is_excel_error(value: Any) -> bool:
    """是否为 Excel 公式错误（应转 NULL，但要写 data_quality_issue）。"""
    if isinstance(value, str):
        return value.strip().upper() in EXCEL_ERROR_TOKENS
    return False


def resolve_sector_from_text(value: Any) -> str | None:
    """把 A 列的文本（"Building"、"Power"、"Transportation"…）解析为 sector_code。

    匹配规则：
      - 占位符 / 错误 → None
      - lower-case strip 后查 SECTOR_NAME_TO_CODE
      - 不在表里 → None（视为"无法解析"，不一定就是冲突）
    """
    if is_placeholder(value) or is_excel_error(value):
        return None
    if not isinstance(value, str):
        return None
    return SECTOR_NAME_TO_CODE.get(value.strip().lower())


# -------------------------------------------------------------------------
# 清洗结果数据类
# -------------------------------------------------------------------------
@dataclass(slots=True, frozen=True)
class NumericResult:
    """clean_numeric 的返回值。"""

    value: float | None
    excel_error: str | None  # 若来源是 #VALUE! 等，原始 token；否则 None


@dataclass(slots=True, frozen=True)
class EfficiencyResult:
    """efficiency 三元组（value / text / unit）。"""

    value: float | None
    text: str | None
    unit: str | None
    excel_error: str | None = None


@dataclass(slots=True, frozen=True)
class CommodityShare:
    """单个商品份额（多商品行会拆成多个）。"""

    code: str
    share_value: float | None
    share_text: str | None


# -------------------------------------------------------------------------
# 清洗实现
# -------------------------------------------------------------------------
def clean_numeric(value: Any) -> NumericResult:
    """通用数值清洗。

    >>> clean_numeric(56.1)
    NumericResult(value=56.1, excel_error=None)
    >>> clean_numeric('-')
    NumericResult(value=None, excel_error=None)
    >>> clean_numeric('#VALUE!')
    NumericResult(value=None, excel_error='#VALUE!')
    """
    if is_placeholder(value):
        return NumericResult(None, None)
    if is_excel_error(value):
        return NumericResult(None, str(value).strip())
    if isinstance(value, bool):  # 防止 True/False 被当成 1/0
        return NumericResult(None, None)
    if isinstance(value, (int, float)):
        return NumericResult(float(value), None)
    if isinstance(value, str):
        text = value.strip()
        # 处理百分号
        if text.endswith("%"):
            try:
                return NumericResult(float(text.rstrip("%")) / 100.0, None)
            except ValueError:
                return NumericResult(None, None)
        try:
            return NumericResult(float(text), None)
        except ValueError:
            return NumericResult(None, None)
    return NumericResult(None, None)


def clean_text(value: Any) -> str | None:
    """通用文本清洗：占位符 / Excel 错误 → None；其他 strip 后保留。"""
    if is_placeholder(value) or is_excel_error(value):
        return None
    if isinstance(value, str):
        return value.strip() or None
    return str(value)


# -------------------------------------------------------------------------
# efficiency 解析（正则分离 value / unit）
# -------------------------------------------------------------------------
_RE_NUM_THEN_UNIT = re.compile(r"^([+-]?\d+(?:\.\d+)?)\s+(.+)$")
_RE_LABEL_NUM = re.compile(r"^([A-Za-z][\w/\s]*?)\s*[:：]\s*([+-]?\d+(?:\.\d+)?)\s*$")


def parse_efficiency(value: Any) -> EfficiencyResult:
    """解析 efficiency 字段。

    支持：
      - 0.497              → value=0.497
      - 'COP: 3.91'        → value=3.91, unit='COP'
      - '13.33 km/litre'   → value=13.33, unit='km/litre'
      - 'NA' / '-' / ''    → 三者皆 None
      - '#VALUE!'          → excel_error 标记
    """
    if is_placeholder(value):
        return EfficiencyResult(None, None, None)
    if is_excel_error(value):
        return EfficiencyResult(None, None, None, str(value).strip())

    if isinstance(value, bool):
        return EfficiencyResult(None, None, None)
    if isinstance(value, (int, float)):
        return EfficiencyResult(float(value), str(value), None)

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return EfficiencyResult(None, None, None)

        # 1) 纯数字
        try:
            return EfficiencyResult(float(text), text, None)
        except ValueError:
            pass

        # 2) "13.33 km/litre"
        m = _RE_NUM_THEN_UNIT.match(text)
        if m:
            try:
                return EfficiencyResult(float(m.group(1)), text, m.group(2).strip())
            except ValueError:
                pass

        # 3) "COP: 3.91"
        m = _RE_LABEL_NUM.match(text)
        if m:
            try:
                return EfficiencyResult(float(m.group(2)), text, m.group(1).strip())
            except ValueError:
                pass

        # 4) 其它文本：只保留原文
        return EfficiencyResult(None, text, None)

    return EfficiencyResult(None, None, None)


# -------------------------------------------------------------------------
# 多商品 / 多份额拆分（'PWRBMS+PWACOA' / '20%+80%'）
# -------------------------------------------------------------------------
_RE_PLUS_SPLIT = re.compile(r"\s*\+\s*")


def parse_commodity_combo(commodity_cell: Any, share_cell: Any) -> list[CommodityShare]:
    """拆分多商品行。

    >>> parse_commodity_combo('PWRBMS+PWACOA', '20%+80%')
    [CommodityShare(code='PWRBMS', share_value=0.2, share_text='20%'),
     CommodityShare(code='PWACOA', share_value=0.8, share_text='80%')]

    >>> parse_commodity_combo('PWRNGA', 1)
    [CommodityShare(code='PWRNGA', share_value=1.0, share_text='1')]

    >>> parse_commodity_combo('-', None)
    []
    """
    if is_placeholder(commodity_cell):
        return []

    codes = [
        c.strip()
        for c in _RE_PLUS_SPLIT.split(str(commodity_cell).strip())
        if c.strip()
    ]
    if not codes:
        return []

    # 解析 share
    if isinstance(share_cell, bool):
        share_pairs: list[tuple[float | None, str | None]] = [(None, None)] * len(codes)
    elif isinstance(share_cell, (int, float)):
        share_pairs = [(float(share_cell), str(share_cell))]
    elif is_placeholder(share_cell) or is_excel_error(share_cell):
        share_pairs = [(None, None)] * len(codes)
    elif isinstance(share_cell, str):
        parts = _RE_PLUS_SPLIT.split(share_cell.strip())
        share_pairs = [_parse_share_token(p) for p in parts]
    else:
        share_pairs = [(None, str(share_cell))] * len(codes)

    # 长度对齐：share 不够时补 (None, None)
    while len(share_pairs) < len(codes):
        share_pairs.append((None, None))

    return [
        CommodityShare(code=code, share_value=pair[0], share_text=pair[1])
        for code, pair in zip(codes, share_pairs[: len(codes)], strict=False)
    ]


def _parse_share_token(token: str) -> tuple[float | None, str | None]:
    """解析单个 share 文本，如 '20%' / '0.2' / 'NA'。"""
    text = token.strip()
    if not text or is_placeholder(text):
        return (None, None)
    if text.endswith("%"):
        try:
            return (float(text.rstrip("%")) / 100.0, text)
        except ValueError:
            return (None, text)
    try:
        return (float(text), text)
    except ValueError:
        return (None, text)
