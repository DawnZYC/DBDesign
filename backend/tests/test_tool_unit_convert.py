"""② convert_unit 单测。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from app.tools.unit_convert import convert_unit  # noqa: E402


def _call(value, frm, to):
    """工具是 LangChain Tool；用 invoke 调。"""
    return convert_unit.invoke({"value": value, "from_unit": frm, "to_unit": to})


def test_pj_to_ktoe():
    out = _call(1.0, "PJ", "ktoe")
    assert out["family"] == "energy"
    # 1 PJ ≈ 23.885 ktoe
    assert abs(out["value"] - 23.885) < 0.01


def test_ktoe_to_pj():
    out = _call(23.885, "ktoe", "PJ")
    assert abs(out["value"] - 1.0) < 1e-3


def test_pj_to_gwh():
    out = _call(1.0, "PJ", "GWh")
    # 1 PJ = 277.78 GWh
    assert abs(out["value"] - 277.778) < 0.1


def test_gwh_to_mwh():
    out = _call(1.0, "GWh", "MWh")
    assert abs(out["value"] - 1000.0) < 1e-6


def test_kt_to_mt_co2():
    out = _call(1500.0, "kt-CO2", "Mt-CO2")
    assert out["family"] == "co2"
    assert abs(out["value"] - 1.5) < 1e-9


def test_t_to_kt_co2():
    out = _call(2500.0, "t-CO2", "kt-CO2")
    assert abs(out["value"] - 2.5) < 1e-9


def test_unicode_subscript_co2():
    """容忍 'kt-CO₂' 这种带下标的写法。"""
    out = _call(100.0, "kt-CO₂", "Mt-CO2")
    assert out["family"] == "co2"
    assert abs(out["value"] - 0.1) < 1e-9


def test_cross_family_rejected():
    with pytest.raises((ValueError, Exception)):
        _call(1.0, "PJ", "kt-CO2")


def test_unknown_unit_rejected():
    with pytest.raises((ValueError, Exception)):
        _call(1.0, "WTF", "PJ")


def test_factor_audit():
    """factor 字段应让人类能复算。"""
    out = _call(2.0, "PJ", "GWh")
    assert abs(out["factor"] - 277.778) < 0.1
    assert abs(out["value"] - 2 * out["factor"]) < 1e-3
