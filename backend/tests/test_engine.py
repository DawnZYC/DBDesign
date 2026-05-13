"""Tests for the converter engine orchestrator."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.converters import engine
from app.converters.base_model import PowerRecord


class TestGetAvailableModels:
    def test_returns_registered_models(self):
        models = engine.get_available_models()
        keys = {m["key"] for m in models}
        # The two converters registered at the time of writing.
        assert {"VT_SG_PWR", "VT_SG_PRI"}.issubset(keys)

    def test_entries_have_required_metadata(self):
        for entry in engine.get_available_models():
            assert "key" in entry
            assert "label" in entry
            assert "sector" in entry
            assert "description" in entry

    def test_does_not_import_heavy_modules(self):
        # Sanity check that the metadata-only listing is callable without raising.
        # (The function intentionally avoids importing pandas/numpy.)
        engine.get_available_models()


class TestConvertUnknownModel:
    def test_unknown_model_returns_error(self, tmp_path):
        result = engine.convert(
            model_name="DOES_NOT_EXIST",
            vt_file_path=str(tmp_path / "src.xlsx"),
            template_path=str(tmp_path / "tmpl.xlsx"),
            output_path=str(tmp_path / "out.xlsx"),
        )
        assert result["success"] is False
        assert any("Unknown model" in e for e in result["errors"])


class _StubConverter:
    """A dependency-free fake converter used to exercise engine.convert."""

    TARGET_SHEET = "Power"

    def __init__(self, file_path: str) -> None:
        self.file_path = file_path

    def extract_power_records(self) -> list[PowerRecord]:
        return [PowerRecord(process_code="STUB", year=2018)]


class _EmptyConverter(_StubConverter):
    def extract_power_records(self) -> list[PowerRecord]:
        return []


class _RaisingConverter(_StubConverter):
    def extract_power_records(self) -> list[PowerRecord]:
        raise RuntimeError("kaboom")


class _KeyErrorConverter(_StubConverter):
    def extract_power_records(self) -> list[PowerRecord]:
        raise KeyError("Mining")


class TestConvertHappyPath:
    def test_success(self, tmp_path):
        out = tmp_path / "out.xlsx"

        def fake_writer(*, records, template_path, output_path, sheet_name):
            assert sheet_name == "Power"
            assert len(records) == 1
            # Touch the file so engine.convert can pretend it was written.
            with open(output_path, "wb") as fh:
                fh.write(b"OK")
            return output_path

        with patch.object(engine, "_build_registry", return_value={"VT_SG_PWR": _StubConverter}):
            with patch.object(engine, "write_output", side_effect=fake_writer):
                result = engine.convert(
                    model_name="VT_SG_PWR",
                    vt_file_path=str(tmp_path / "src.xlsx"),
                    template_path=str(tmp_path / "tmpl.xlsx"),
                    output_path=str(out),
                )

        assert result["success"] is True
        assert result["row_count"] == 1
        assert result["sheet_name"] == "Power"
        assert result["errors"] == []


class TestConvertFailurePaths:
    def test_no_records_extracted(self, tmp_path):
        with patch.object(engine, "_build_registry", return_value={"VT_SG_PWR": _EmptyConverter}):
            result = engine.convert(
                model_name="VT_SG_PWR",
                vt_file_path=str(tmp_path / "src.xlsx"),
                template_path=str(tmp_path / "tmpl.xlsx"),
                output_path=str(tmp_path / "out.xlsx"),
            )
        assert result["success"] is False
        assert any("No records" in e for e in result["errors"])

    def test_converter_raises_keyerror(self, tmp_path):
        with patch.object(
            engine, "_build_registry", return_value={"VT_SG_PWR": _KeyErrorConverter}
        ):
            result = engine.convert(
                model_name="VT_SG_PWR",
                vt_file_path=str(tmp_path / "src.xlsx"),
                template_path=str(tmp_path / "tmpl.xlsx"),
                output_path=str(tmp_path / "out.xlsx"),
            )
        assert result["success"] is False
        assert any("Missing expected sheet" in e for e in result["errors"])

    def test_converter_raises_generic(self, tmp_path):
        with patch.object(
            engine, "_build_registry", return_value={"VT_SG_PWR": _RaisingConverter}
        ):
            result = engine.convert(
                model_name="VT_SG_PWR",
                vt_file_path=str(tmp_path / "src.xlsx"),
                template_path=str(tmp_path / "tmpl.xlsx"),
                output_path=str(tmp_path / "out.xlsx"),
            )
        assert result["success"] is False
        assert any("Conversion error" in e for e in result["errors"])

    def test_registry_import_failure(self, tmp_path):
        with patch.object(
            engine,
            "_build_registry",
            side_effect=RuntimeError("dependency missing"),
        ):
            result = engine.convert(
                model_name="VT_SG_PWR",
                vt_file_path=str(tmp_path / "src.xlsx"),
                template_path=str(tmp_path / "tmpl.xlsx"),
                output_path=str(tmp_path / "out.xlsx"),
            )
        assert result["success"] is False
        assert any("dependency missing" in e for e in result["errors"])

    def test_metadata_known_but_class_missing(self, tmp_path):
        # Registered in MODEL_METADATA but the registry happens to omit the class.
        with patch.object(engine, "_build_registry", return_value={}):
            result = engine.convert(
                model_name="VT_SG_PWR",
                vt_file_path=str(tmp_path / "src.xlsx"),
                template_path=str(tmp_path / "tmpl.xlsx"),
                output_path=str(tmp_path / "out.xlsx"),
            )
        assert result["success"] is False
        assert any("registered in metadata" in e for e in result["errors"])
