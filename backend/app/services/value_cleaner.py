"""Cell value cleaning rules.

The three cleaning rules match the ER diagram v2 design:
  1. Placeholders ('-' / 'NA' / '' / whitespace) become SQL NULL.
  2. Formula errors such as #VALUE! become NULL in main tables and create data_quality_issue rows.
  3. Mixed semantic text such as 'COP: 3.91' is split into value / text / unit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# -------------------------------------------------------------------------
# Constants
# -------------------------------------------------------------------------
PLACEHOLDER_LITERALS: frozenset[str] = frozenset(
    {"", "-", "—", "na", "n/a", "n.a.", "null", "none"}
)

EXCEL_ERROR_TOKENS: frozenset[str] = frozenset(
    {"#VALUE!", "#REF!", "#DIV/0!", "#N/A", "#NAME?", "#NULL!", "#NUM!"}
)

# Fuzzy mapping from column A text to sector_code, allowing synonyms and plurals.
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
# Predicates
# -------------------------------------------------------------------------
def is_placeholder(value: Any) -> bool:
    """Return whether the value is a placeholder that should become NULL without a trace."""
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in PLACEHOLDER_LITERALS
    return False


def is_excel_error(value: Any) -> bool:
    """Return whether the value is an Excel formula error that should create a data_quality_issue."""
    if isinstance(value, str):
        return value.strip().upper() in EXCEL_ERROR_TOKENS
    return False


def resolve_sector_from_text(value: Any) -> str | None:
    """Resolve column A text such as "Building", "Power", or "Transportation" to sector_code.

    Matching rules:
      - Placeholder or error values become None.
      - Strip and lower-case text before looking it up in SECTOR_NAME_TO_CODE.
      - Unknown values become None, meaning unresolved but not necessarily conflicting.
    """
    if is_placeholder(value) or is_excel_error(value):
        return None
    if not isinstance(value, str):
        return None
    return SECTOR_NAME_TO_CODE.get(value.strip().lower())


# -------------------------------------------------------------------------
# Cleaning result data classes
# -------------------------------------------------------------------------
@dataclass(slots=True, frozen=True)
class NumericResult:
    """Return value for clean_numeric."""

    value: float | None
    excel_error: str | None  # Original token for #VALUE! and similar errors, otherwise None.


@dataclass(slots=True, frozen=True)
class EfficiencyResult:
    """Efficiency triple: value / text / unit."""

    value: float | None
    text: str | None
    unit: str | None
    excel_error: str | None = None


@dataclass(slots=True, frozen=True)
class CommodityShare:
    """Single commodity share; multi-commodity rows are split into multiple items."""

    code: str
    share_value: float | None
    share_text: str | None


# -------------------------------------------------------------------------
# Cleaning implementation
# -------------------------------------------------------------------------
def clean_numeric(value: Any) -> NumericResult:
    """Clean a generic numeric value.

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
    if isinstance(value, bool):  # Avoid treating True/False as 1/0.
        return NumericResult(None, None)
    if isinstance(value, int | float):
        return NumericResult(float(value), None)
    if isinstance(value, str):
        text = value.strip()
        # Handle percentages.
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
    """Clean generic text: placeholders and Excel errors become None; other values are stripped."""
    if is_placeholder(value) or is_excel_error(value):
        return None
    if isinstance(value, str):
        return value.strip() or None
    return str(value)


# -------------------------------------------------------------------------
# Efficiency parsing with regex-based value / unit splitting.
# -------------------------------------------------------------------------
_RE_NUM_THEN_UNIT = re.compile(r"^([+-]?\d+(?:\.\d+)?)\s+(.+)$")
_RE_LABEL_NUM = re.compile(r"^([A-Za-z][\w/\s]*?)\s*[:：]\s*([+-]?\d+(?:\.\d+)?)\s*$")


def parse_efficiency(value: Any) -> EfficiencyResult:
    """Parse the efficiency field.

    Supported examples:
      - 0.497              -> value=0.497
      - 'COP: 3.91'        -> value=3.91, unit='COP'
      - '13.33 km/litre'   -> value=13.33, unit='km/litre'
      - 'NA' / '-' / ''    -> all fields None
      - '#VALUE!'          -> excel_error marker
    """
    if is_placeholder(value):
        return EfficiencyResult(None, None, None)
    if is_excel_error(value):
        return EfficiencyResult(None, None, None, str(value).strip())

    if isinstance(value, bool):
        return EfficiencyResult(None, None, None)
    if isinstance(value, int | float):
        return EfficiencyResult(float(value), str(value), None)

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return EfficiencyResult(None, None, None)

        # 1) Plain number.
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

        # 4) Other text: keep the original text only.
        return EfficiencyResult(None, text, None)

    return EfficiencyResult(None, None, None)


# -------------------------------------------------------------------------
# Multi-commodity / multi-share splitting ('PWRBMS+PWACOA' / '20%+80%').
# -------------------------------------------------------------------------
_RE_PLUS_SPLIT = re.compile(r"\s*\+\s*")


def parse_commodity_combo(commodity_cell: Any, share_cell: Any) -> list[CommodityShare]:
    """Split a multi-commodity row.

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

    codes = [c.strip() for c in _RE_PLUS_SPLIT.split(str(commodity_cell).strip()) if c.strip()]
    if not codes:
        return []

    # Parse share.
    if isinstance(share_cell, bool):
        share_pairs: list[tuple[float | None, str | None]] = [(None, None)] * len(codes)
    elif isinstance(share_cell, int | float):
        share_pairs = [(float(share_cell), str(share_cell))]
    elif is_placeholder(share_cell) or is_excel_error(share_cell):
        share_pairs = [(None, None)] * len(codes)
    elif isinstance(share_cell, str):
        parts = _RE_PLUS_SPLIT.split(share_cell.strip())
        share_pairs = [_parse_share_token(p) for p in parts]
    else:
        share_pairs = [(None, str(share_cell))] * len(codes)

    # Align lengths: pad missing share values with (None, None).
    while len(share_pairs) < len(codes):
        share_pairs.append((None, None))

    return [
        CommodityShare(code=code, share_value=pair[0], share_text=pair[1])
        for code, pair in zip(codes, share_pairs[: len(codes)], strict=False)
    ]


def _parse_share_token(token: str) -> tuple[float | None, str | None]:
    """Parse one share token such as '20%', '0.2', or 'NA'."""
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
