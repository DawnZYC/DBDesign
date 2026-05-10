"""Orchestrates the conversion pipeline.

The catalog of registered models lives in :data:`MODEL_METADATA` so that
clients can list available converters without importing pandas / numpy. The
heavy converter modules are only loaded when an actual conversion runs.

To register a new model:
  1. Add an entry to :data:`MODEL_METADATA` keyed by its stable identifier.
  2. Add an entry to :func:`_build_registry` mapping that key to the converter
     class.
"""

from __future__ import annotations

import logging
from typing import Type

from app.converters.ecotea_writer import write_output


logger = logging.getLogger(__name__)


# Public metadata returned to the UI. Source of truth for *which* models
# exist; importing the actual converter classes is deferred so this listing
# stays cheap and resilient to optional-deps failures (pandas, numpy, ...).
MODEL_METADATA: dict[str, dict[str, str]] = {
    "VT_SG_PWR": {
        "label": "VT_SG_PWR — Power",
        "sector": "Power",
        "description": "Singapore power generation processes (VT_SG_PWR_GREF).",
    },
    "VT_SG_PRI": {
        "label": "VT_SG_PRI — Primary",
        "sector": "Primary",
        "description": "Singapore primary import and mining processes (VT_SG_PRI_GREF).",
    },
}


def get_available_models() -> list[dict[str, str]]:
    """Return the public list of registered models for the UI.

    This intentionally avoids importing the converter modules so it remains
    callable even when heavy optional dependencies are missing.
    """
    return [{"key": key, **meta} for key, meta in MODEL_METADATA.items()]


def _build_registry() -> dict[str, Type]:
    """Lazily import and return ``{key: converter_class}`` mappings.

    Wrapped in a helpful error so a missing ``pandas`` install surfaces as a
    readable message rather than a generic ``ModuleNotFoundError``.
    """
    try:
        from app.converters.models.vt_sg_pri import VTSGPRIConverter
        from app.converters.models.vt_sg_pwr import VTSGPWRConverter
    except ModuleNotFoundError as exc:
        logger.exception("Failed to load converter modules")
        raise RuntimeError(
            "Conversion engine could not be loaded. Required dependencies "
            f"are missing: {exc.name}. Install backend requirements with "
            "`pip install -r requirements.txt`."
        ) from exc

    return {
        "VT_SG_PWR": VTSGPWRConverter,
        "VT_SG_PRI": VTSGPRIConverter,
    }


def convert(
    *,
    model_name: str,
    vt_file_path: str,
    template_path: str,
    output_path: str,
) -> dict:
    """Run the conversion pipeline.

    Returns a result dict with keys ``success``, ``output_path``, ``row_count``,
    ``errors``, and (when successful) ``sheet_name``.
    """
    if model_name not in MODEL_METADATA:
        return {
            "success": False,
            "errors": [
                f"Unknown model '{model_name}'. Available: {list(MODEL_METADATA.keys())}",
            ],
        }

    try:
        registry = _build_registry()
    except RuntimeError as exc:
        return {"success": False, "errors": [str(exc)]}

    if model_name not in registry:
        return {
            "success": False,
            "errors": [
                f"Model '{model_name}' is registered in metadata but its "
                "converter class could not be loaded.",
            ],
        }

    errors: list[str] = []
    try:
        converter_cls = registry[model_name]
        converter = converter_cls(vt_file_path)
        records = converter.extract_power_records()

        if not records:
            errors.append(
                "No records were extracted from the source file. "
                "Verify that the file matches the selected model.",
            )
            return {"success": False, "errors": errors}

        target_sheet = getattr(converter_cls, "TARGET_SHEET", "Power")
        write_output(
            records=records,
            template_path=template_path,
            output_path=output_path,
            sheet_name=target_sheet,
        )

        return {
            "success": True,
            "output_path": str(output_path),
            "row_count": len(records),
            "sheet_name": target_sheet,
            "errors": [],
        }

    except KeyError as exc:
        errors.append(
            f"Missing expected sheet or column in the source file: {exc}. "
            f"Is this really a {model_name} workbook?",
        )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Conversion error: {type(exc).__name__}: {exc}")

    return {"success": False, "errors": errors}
