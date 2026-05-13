"""Unit tests for app.services.value_cleaner.

These tests cover the pure cleaning helpers used by the import pipeline.
They are deliberately independent of FastAPI / SQLAlchemy fixtures so they
exercise the logic in isolation and run quickly.
"""

from __future__ import annotations

import pytest

from app.services.value_cleaner import (
    CommodityShare,
    EfficiencyResult,
    NumericResult,
    _parse_share_token,
    clean_numeric,
    clean_text,
    is_excel_error,
    is_placeholder,
    parse_commodity_combo,
    parse_efficiency,
    resolve_sector_from_text,
)


# ---------------------------------------------------------------------------
# is_placeholder
# ---------------------------------------------------------------------------
class TestIsPlaceholder:
    @pytest.mark.parametrize(
        "value",
        [None, "", " ", "-", "—", "NA", "na", "N/A", "n.a.", "Null", "none", "  -  "],
    )
    def test_returns_true_for_known_placeholders(self, value):
        assert is_placeholder(value) is True

    @pytest.mark.parametrize("value", [0, 0.0, False, "0", "x", "actual text", 3.14])
    def test_returns_false_for_real_values(self, value):
        assert is_placeholder(value) is False


# ---------------------------------------------------------------------------
# is_excel_error
# ---------------------------------------------------------------------------
class TestIsExcelError:
    @pytest.mark.parametrize(
        "token",
        ["#VALUE!", "#REF!", "#DIV/0!", "#N/A", "#NAME?", "#NULL!", "#NUM!"],
    )
    def test_detects_known_error_tokens(self, token):
        assert is_excel_error(token) is True
        # Case-insensitive and whitespace-tolerant.
        assert is_excel_error(f"  {token.lower()}  ") is True

    @pytest.mark.parametrize("value", ["", "-", "ok", 1.0, None, "#FOO!"])
    def test_non_error_values(self, value):
        assert is_excel_error(value) is False


# ---------------------------------------------------------------------------
# resolve_sector_from_text
# ---------------------------------------------------------------------------
class TestResolveSectorFromText:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("Power", "POWER"),
            ("power", "POWER"),
            ("  Power  ", "POWER"),
            ("Industry", "INDUSTRY"),
            ("industries", "INDUSTRY"),
            ("Transportation", "TRANSPORT"),
            ("Buildings", "BUILDING"),
            ("Agriculture", "AGRI"),
            ("agricultural", "AGRI"),
            ("Households", "HOUSEHOLD"),
            ("InfoComm", "INFOCOMM"),
            ("ICT", "INFOCOMM"),
        ],
    )
    def test_known_sector_names(self, text, expected):
        assert resolve_sector_from_text(text) == expected

    @pytest.mark.parametrize("value", [None, "", "-", "#VALUE!", "Unknown Sector", 123])
    def test_unresolvable_returns_none(self, value):
        assert resolve_sector_from_text(value) is None


# ---------------------------------------------------------------------------
# clean_numeric
# ---------------------------------------------------------------------------
class TestCleanNumeric:
    def test_real_number(self):
        result = clean_numeric(56.1)
        assert result == NumericResult(value=56.1, excel_error=None)

    def test_int_coerced_to_float(self):
        result = clean_numeric(7)
        assert result.value == 7.0
        assert result.excel_error is None

    def test_placeholder_returns_none(self):
        assert clean_numeric("-") == NumericResult(None, None)
        assert clean_numeric(None) == NumericResult(None, None)

    def test_excel_error_recorded(self):
        result = clean_numeric("#VALUE!")
        assert result.value is None
        assert result.excel_error == "#VALUE!"

    def test_boolean_rejected(self):
        # Booleans must not be coerced to 1/0.
        assert clean_numeric(True) == NumericResult(None, None)
        assert clean_numeric(False) == NumericResult(None, None)

    def test_string_number_parsed(self):
        assert clean_numeric("3.14").value == pytest.approx(3.14)
        assert clean_numeric("  -2  ").value == -2.0

    def test_percentage_string(self):
        assert clean_numeric("20%").value == pytest.approx(0.2)
        assert clean_numeric("100%").value == pytest.approx(1.0)

    def test_invalid_percentage(self):
        assert clean_numeric("abc%") == NumericResult(None, None)

    def test_unparseable_text(self):
        assert clean_numeric("not a number") == NumericResult(None, None)

    def test_unsupported_type(self):
        assert clean_numeric([1, 2]) == NumericResult(None, None)


# ---------------------------------------------------------------------------
# clean_text
# ---------------------------------------------------------------------------
class TestCleanText:
    def test_strips_whitespace(self):
        assert clean_text("  hello  ") == "hello"

    def test_placeholder_becomes_none(self):
        assert clean_text("-") is None
        assert clean_text(None) is None
        assert clean_text("") is None

    def test_excel_error_becomes_none(self):
        assert clean_text("#REF!") is None

    def test_empty_after_strip_becomes_none(self):
        assert clean_text("   ") is None

    def test_non_string_coerced(self):
        assert clean_text(42) == "42"


# ---------------------------------------------------------------------------
# parse_efficiency
# ---------------------------------------------------------------------------
class TestParseEfficiency:
    def test_plain_number_float(self):
        result = parse_efficiency(0.497)
        assert result.value == pytest.approx(0.497)
        assert result.unit is None
        assert result.excel_error is None

    def test_plain_number_string(self):
        result = parse_efficiency("0.42")
        assert result.value == pytest.approx(0.42)
        assert result.text == "0.42"
        assert result.unit is None

    def test_number_with_unit(self):
        result = parse_efficiency("13.33 km/litre")
        assert result.value == pytest.approx(13.33)
        assert result.unit == "km/litre"
        assert result.text == "13.33 km/litre"

    def test_label_with_number(self):
        result = parse_efficiency("COP: 3.91")
        assert result.value == pytest.approx(3.91)
        assert result.unit == "COP"

    def test_placeholder(self):
        assert parse_efficiency("NA") == EfficiencyResult(None, None, None)
        assert parse_efficiency("-") == EfficiencyResult(None, None, None)
        assert parse_efficiency("") == EfficiencyResult(None, None, None)

    def test_excel_error(self):
        result = parse_efficiency("#VALUE!")
        assert result.value is None
        assert result.excel_error == "#VALUE!"

    def test_arbitrary_text_keeps_text_only(self):
        result = parse_efficiency("complicated formula text")
        assert result.value is None
        assert result.text == "complicated formula text"
        assert result.unit is None

    def test_boolean_rejected(self):
        assert parse_efficiency(True) == EfficiencyResult(None, None, None)

    def test_unsupported_type(self):
        assert parse_efficiency([1]) == EfficiencyResult(None, None, None)

    def test_whitespace_only_string(self):
        assert parse_efficiency("   ") == EfficiencyResult(None, None, None)


# ---------------------------------------------------------------------------
# parse_commodity_combo
# ---------------------------------------------------------------------------
class TestParseCommodityCombo:
    def test_multi_commodity_with_percent_shares(self):
        result = parse_commodity_combo("PWRBMS+PWACOA", "20%+80%")
        assert result == [
            CommodityShare(code="PWRBMS", share_value=0.2, share_text="20%"),
            CommodityShare(code="PWACOA", share_value=0.8, share_text="80%"),
        ]

    def test_single_commodity_numeric_share(self):
        result = parse_commodity_combo("PWRNGA", 1)
        assert result == [CommodityShare(code="PWRNGA", share_value=1.0, share_text="1")]

    def test_placeholder_commodity(self):
        assert parse_commodity_combo("-", None) == []
        assert parse_commodity_combo("NA", "0.5") == []

    def test_boolean_share(self):
        result = parse_commodity_combo("PWRNGA", True)
        assert result == [CommodityShare(code="PWRNGA", share_value=None, share_text=None)]

    def test_placeholder_share_yields_none(self):
        result = parse_commodity_combo("PWRBMS+PWACOA", "-")
        assert result == [
            CommodityShare(code="PWRBMS", share_value=None, share_text=None),
            CommodityShare(code="PWACOA", share_value=None, share_text=None),
        ]

    def test_share_count_shorter_than_codes_pads_with_none(self):
        result = parse_commodity_combo("A+B+C", "0.5")
        codes = [r.code for r in result]
        # Numeric share is broadcast as the only pair, then padded for B/C.
        assert codes == ["A", "B", "C"]
        assert result[0].share_value == pytest.approx(0.5)
        assert result[1].share_value is None
        assert result[2].share_value is None

    def test_share_count_longer_than_codes_truncates(self):
        result = parse_commodity_combo("X", "10%+20%+30%")
        assert len(result) == 1
        assert result[0].code == "X"
        assert result[0].share_value == pytest.approx(0.1)

    def test_decimal_share_text(self):
        result = parse_commodity_combo("AAA+BBB", "0.3+0.7")
        assert [r.share_value for r in result] == [
            pytest.approx(0.3),
            pytest.approx(0.7),
        ]

    def test_unparseable_share_token_keeps_text(self):
        result = parse_commodity_combo("X+Y", "abc+50%")
        assert result[0].share_value is None
        assert result[0].share_text == "abc"
        assert result[1].share_value == pytest.approx(0.5)

    def test_empty_commodity_string(self):
        assert parse_commodity_combo("", 1) == []

    def test_unsupported_share_type_falls_back_to_text(self):
        result = parse_commodity_combo("AAA", object())
        assert len(result) == 1
        assert result[0].share_value is None
        # text is the str() of the share_cell
        assert result[0].share_text is not None


# ---------------------------------------------------------------------------
# _parse_share_token (internal helper, but worth covering its branches)
# ---------------------------------------------------------------------------
class TestParseShareToken:
    def test_percent(self):
        assert _parse_share_token("25%") == (pytest.approx(0.25), "25%")

    def test_decimal(self):
        assert _parse_share_token("0.5") == (pytest.approx(0.5), "0.5")

    def test_placeholder(self):
        assert _parse_share_token("-") == (None, None)
        assert _parse_share_token("") == (None, None)

    def test_invalid_percent(self):
        val, text = _parse_share_token("abc%")
        assert val is None
        assert text == "abc%"

    def test_invalid_decimal(self):
        val, text = _parse_share_token("abc")
        assert val is None
        assert text == "abc"
