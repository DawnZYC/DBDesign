"""Tests for the PowerRecord dataclass / BaseConverter contract."""

from __future__ import annotations

import pytest

from app.converters.base_model import MISSING, BaseConverter, PowerRecord


class TestMissingSentinel:
    def test_value(self):
        # The MISSING sentinel is the EcoTEA placeholder '-' string.
        assert MISSING == "-"


class TestPowerRecord:
    def test_defaults(self):
        rec = PowerRecord()
        # Defaults must produce a row with the MISSING placeholder in most cells.
        assert rec.wp6_title == "Power"
        assert rec.data_owner == MISSING
        assert rec.process_code == MISSING
        assert rec.year == 2018
        assert rec.start_year == 2018
        assert rec.ef_unit == "PJ"
        assert rec.currency == "MSGD2016"
        assert rec.capex_unit == "GW"
        assert rec.fixed_opex_unit == "GW*yr(2018)"
        assert rec.variable_opex_unit == "PJ (2018)"

    def test_full_assignment_roundtrip(self):
        rec = PowerRecord(
            wp6_title="Primary",
            data_owner="ESI",
            data_provider="WP1",
            data_source="GREF",
            process_code="PWRNGACCF01",
            description="Combined cycle gas turbine",
            geography="SG",
            year=2030,
            start_year=2018,
            lifetime=25,
            ef=56.1,
            capex=900.0,
            commodity="PWRNGA",
            commodity_share=1,
            afa=0.85,
        )
        assert rec.process_code == "PWRNGACCF01"
        assert rec.lifetime == 25
        assert rec.ef == 56.1
        assert rec.commodity_share == 1
        assert rec.afa == 0.85


class _FakeConverter(BaseConverter):
    """Minimal subclass for testing the abstract base class hooks."""

    def extract_power_records(self) -> list[PowerRecord]:
        # Returns a deterministic single-row payload so we can assert through it.
        return [PowerRecord(process_code="FAKE", description="fake")]


class TestBaseConverter:
    def test_init_stores_file_path(self):
        conv = _FakeConverter("some/path.xlsx")
        assert conv.file_path == "some/path.xlsx"
        assert conv._sheets == {}

    def test_extract_returns_records(self):
        conv = _FakeConverter("dummy.xlsx")
        records = conv.extract_power_records()
        assert len(records) == 1
        assert records[0].process_code == "FAKE"

    def test_cannot_instantiate_abstract_base(self):
        with pytest.raises(TypeError):
            BaseConverter("dummy.xlsx")  # type: ignore[abstract]
