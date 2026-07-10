"""Schema-Mapping Agent (M5) — auto-align column-layout changes across template versions.

Positioning (decoupled from M3's query agents):
  * M3's Planner->SQL->Interpreter->Visualizer is the **query-time** LangGraph pipeline.
  * This module is a standalone **ingestion-time** Agent, not part of that graph; it is
    called separately by the import flow.

The problem it solves:
  The existing excel_importer hard-codes column positions (capex is always column R, ef
  is always column O, ...), assuming the input Excel matches the canonical template layout
  exactly. Once the upstream model changes version — columns renamed / reordered / added /
  removed — column R is no longer capex and the import silently misaligns.

This module fills that gap:
  Given the headers of an unfamiliar Excel, it produces a mapping `{source column ->
  canonical column}` so that after "relocation" the importer's hard-coded
  `field_to_column` still holds. The importer doesn't change a line.

Two paths:
  1. Fast path: headers match the canonical template -> headers_match_canonical() returns
     True -> no LLM call, go straight to the original hard-coded import (the 99% daily case,
     zero cost).
  2. Slow path: headers don't match -> map_columns() does semantic matching and assigns a
     confidence per column:
       confidence >= 0.9        auto-apply
       0.6 <= confidence < 0.9   send to human review (write data_quality_issue / frontend alignment)
       confidence < 0.6         treated as unmatched, left NULL

Matching has two backends, switched via `use_llm`:
  * LLM backend: llm.with_structured_output(ColumnMapping), strongly typed, hallucination-safe fields.
  * Deterministic backend: pure token/alias matching, **no API key needed**, for CI / offline / LLM fallback.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from dataclasses import field as dc_field

from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Header rows: template row 2 is the most readable primary header; rows 1/3-9 hold the
# WP-layer supplementary aliases. For semantic matching we concatenate the text of rows
# 1-9 in the same column into one "header blob" to give the matcher maximum signal.
HEADER_ROW_RANGE = range(1, 10)
PRIMARY_HEADER_ROW = 2


# -----------------------------------------------------------------------------
# Standard field table (single source of truth)
#   column is the canonical position hard-coded in the importer; label is the human
#   header in template row 2; aliases cover the upstream WP layers / common rename synonyms.
# -----------------------------------------------------------------------------
@dataclass(frozen=True)
class FieldSpec:
    field: str  # standard field name (business semantics)
    column: str  # canonical position (Excel column letter, the one hard-coded in the importer)
    label: str  # template primary header (row 2)
    description: str  # field description for the LLM
    aliases: tuple[str, ...] = dc_field(default_factory=tuple)


STANDARD_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(
        "wp_title",
        "A",
        "WP6 Title",
        "Work-package title / owning sector label (also the source of sector text)",
        ("wp title", "wp6 title", "sector", "work package", "title"),
    ),
    FieldSpec(
        "data_owner", "B", "data owner", "Data owner", ("owner", "owner of data", "data owner")
    ),
    FieldSpec(
        "data_provider",
        "C",
        "data provider",
        "Data provider",
        ("provider", "data provider", "source provider"),
    ),
    FieldSpec(
        "data_source",
        "D",
        "data source",
        "Data source / model run name",
        ("source", "data source", "model run name", "dataset"),
    ),
    FieldSpec(
        "data_source_description",
        "E",
        "data source description",
        "Data source description",
        ("source description", "data source desc", "source desc"),
    ),
    FieldSpec("data_user", "F", "data user", "Data user", ("user", "data user")),
    FieldSpec(
        "usage_purpose", "G", "usage purpose", "Usage purpose", ("purpose", "usage", "usage purpose")
    ),
    FieldSpec(
        "technology_code",
        "H",
        "technology/process",
        "Technology / process code (anchor primary key)",
        (
            "technology",
            "process",
            "tech",
            "asset name",
            "technology/process",
            "tech code",
            "technology code",
        ),
    ),
    FieldSpec(
        "technology_description",
        "I",
        "technology/process description",
        "Technology / process description",
        ("technology description", "process description", "asset description", "tech desc"),
    ),
    FieldSpec(
        "geography",
        "J",
        "Geography",
        "Geography / country / region",
        ("geography", "country", "region", "geo"),
    ),
    FieldSpec(
        "data_year",
        "K",
        "year of data",
        "Data year (the anchor's time dimension)",
        ("year", "year of data", "data year"),
    ),
    FieldSpec(
        "technology_start_year",
        "L",
        "Technology Start Year",
        "Earliest build / start year of the technology",
        ("start year", "technology start year", "earliest build year", "ncap_start"),
    ),
    FieldSpec(
        "technology_lifetime_years",
        "M",
        "technology lifetime (years)",
        "Technology lifetime (years)",
        ("lifetime", "technology lifetime", "tlife", "ncap_tlife"),
    ),
    FieldSpec("grade", "N", "Grade", "Grade / tier", ("grade",)),
    FieldSpec(
        "emission_factor",
        "O",
        "ef",
        "Emission factor",
        ("ef", "emission factor", "emissions factor", "vda_emcb", "emcb"),
    ),
    FieldSpec(
        "emission_factor_unit",
        "P",
        "ef ref unit",
        "Emission factor reference unit",
        ("ef unit", "ef ref unit", "emission factor unit"),
    ),
    FieldSpec(
        "base_currency",
        "Q",
        "base currency",
        "Base currency (numerator)",
        ("currency", "base currency", "numerator currency"),
    ),
    FieldSpec(
        "capex",
        "R",
        "capex",
        "Capital expenditure",
        ("capex", "build cost", "investment", "capital cost", "ncap_cost", "capital expenditure"),
    ),
    FieldSpec(
        "capex_unit",
        "S",
        "capex ref unit",
        "Capex reference unit (denominator)",
        ("capex unit", "capex ref unit", "capacity unit"),
    ),
    FieldSpec(
        "fixed_opex",
        "T",
        "fixed opex",
        "Fixed O&M cost",
        ("fixed opex", "fom", "fo&m", "fixed o&m", "ncap_fom", "fixed operating cost"),
    ),
    FieldSpec(
        "fixed_opex_unit",
        "U",
        "fixed opex ref unit",
        "Fixed O&M reference unit",
        ("fixed opex unit", "fom unit", "fixed opex ref unit"),
    ),
    FieldSpec(
        "variable_opex",
        "V",
        "variable opex",
        "Variable O&M cost",
        ("variable opex", "vom", "vo&m", "act_cost", "variable operating cost"),
    ),
    FieldSpec(
        "variable_opex_unit",
        "W",
        "variable opex ref unit",
        "Variable O&M reference unit",
        ("variable opex unit", "vom unit", "variable opex ref unit", "activity unit"),
    ),
    FieldSpec("tax_cost", "X", "Tax cost", "Tax cost", ("tax", "tax cost")),
    FieldSpec("subsidy_cost", "Y", "Sub cost", "Subsidy cost", ("subsidy", "sub cost", "subsidy cost")),
    FieldSpec(
        "efficiency", "Z", "efficiency", "Efficiency (WP-specific technology descriptor)", ("efficiency", "act_eff", "eff")
    ),
    FieldSpec(
        "technology_efficiency",
        "AA",
        "technology efficiency",
        "Technology efficiency",
        ("technology efficiency", "tech efficiency"),
    ),
    FieldSpec(
        "commodity_share",
        "AB",
        "commodity share",
        "Commodity share",
        ("commodity share", "flo_share", "share", "by energy use"),
    ),
    FieldSpec(
        "commodity_code", "AC", "commodity", "Commodity code", ("commodity", "commodity code", "fuel")
    ),
    FieldSpec(
        "commodity_demand", "AD", "Commodity Demand", "Commodity demand", ("commodity demand", "demand")
    ),
    FieldSpec(
        "interpolation_rule",
        "AE",
        "Interpolation rule",
        "Interpolation rule",
        ("interpolation rule", "interpolation", "interp rule"),
    ),
    FieldSpec(
        "capacity_to_activity_factor",
        "AF",
        "capacity to activity factor",
        "Capacity-to-activity factor",
        ("capacity to activity factor", "afa", "c2a"),
    ),
    FieldSpec("heat_rate", "AG", "heat rate", "Heat rate", ("heat rate", "heatrate")),
    FieldSpec(
        "capacity",
        "AH",
        "capacity",
        "Capacity constraint value",
        ("capacity", "wp1 constraints", "capacity constraint"),
    ),
    FieldSpec(
        "bound_type",
        "AI",
        "capacity type",
        "Capacity constraint type (fixed/up/lo)",
        ("capacity type", "bound type", "capacity constraint type"),
    ),
    FieldSpec(
        "max_import_possible",
        "AJ",
        "max import possible",
        "Maximum import possible",
        ("max import possible", "act_bnd", "max import"),
    ),
    FieldSpec(
        "max_solar_output_allowed",
        "AK",
        "max solar output allowed",
        "Maximum allowed solar output",
        ("max solar output allowed", "uc_rhsrt", "max solar output"),
    ),
    # Note: label must match the template row-2 text exactly (headers_match_canonical depends on it).
    # In the template both AH and AL have "capacity" in row 2; semantics are distinguished via
    # aliases / description. The "uc_rhsrt" alias is reserved for AK (whose blob also carries the
    # strong "max solar output allowed" signal), to avoid AK / AL fighting over the same alias in
    # deterministic matching.
    FieldSpec(
        "capacity_special",
        "AL",
        "capacity",
        "Special capacity constraint (UC right-hand-side term UC_RHSRT, distinct from AH's regular capacity constraint)",
        ("capacity special", "special capacity", "uc capacity"),
    ),
)

# Indexes
FIELD_BY_NAME: dict[str, FieldSpec] = {f.field: f for f in STANDARD_FIELDS}
FIELD_BY_COLUMN: dict[str, FieldSpec] = {f.column: f for f in STANDARD_FIELDS}
STANDARD_FIELD_NAMES: tuple[str, ...] = tuple(f.field for f in STANDARD_FIELDS)


# -----------------------------------------------------------------------------
# Structured-output schema (the LLM is strongly constrained via with_structured_output)
# -----------------------------------------------------------------------------
class ColumnSuggestion(BaseModel):
    """Match result for a single column."""

    excel_column: str = Field(..., description="Column letter in the unfamiliar Excel, e.g. 'A'/'B'/'AB'")
    excel_header: str = Field(default="", description="Original header text of this column")
    target_field: str | None = Field(
        default=None,
        description="Matched standard field name (one of STANDARD_FIELD_NAMES); null when no match",
    )
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Confidence in [0, 1]")
    reasoning: str = Field(default="", description="Short reason for the match")


class ColumnMapping(BaseModel):
    """Column match result for the whole sheet."""

    suggestions: list[ColumnSuggestion] = Field(default_factory=list)


# Confidence thresholds (consistent with PlanReadme M5)
AUTO_APPLY_THRESHOLD = 0.9
REVIEW_THRESHOLD = 0.6

# Quality gate for auto-apply (the third tier of the "many renames -> reject and warn" acceptance)
#   - core columns: sources of the anchor primary key; missing them yields empty/dirty data
#   - coverage: auto-aligned columns / standard fields below this means the layout changed
#     too much to import blindly
CORE_FIELDS: tuple[str, ...] = ("technology_code", "data_year")
MIN_AUTO_MAPPED_RATIO = 0.5


class SchemaMappingRejected(ValueError):  # noqa: N818 - public API name kept stable
    """Auto column alignment failed the quality gate; refuse a silent import.

    Caught by the import flow and turned into a 4xx, prompting the user to go through the
    column-alignment review in preview (manual override).
    """


# -----------------------------------------------------------------------------
# Header reading & normalization
# -----------------------------------------------------------------------------
def _normalize(text: object) -> str:
    """Lowercase, strip punctuation, collapse whitespace, for robust comparison."""
    s = str(text or "").lower()
    s = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", s)  # keep CJK so Chinese headers still normalize
    return re.sub(r"\s+", " ", s).strip()


def _tokens(text: str) -> set[str]:
    return {t for t in _normalize(text).split() if t}


def extract_header_blobs(
    worksheet: Worksheet, *, header_rows: Iterable[int] = HEADER_ROW_RANGE
) -> dict[str, str]:
    """Concatenate the non-empty header text (rows 1-9) per column into one blob; return {column letter: blob}.

    Implemented with iter_rows, so it works in both read_only and normal modes.
    Only columns with at least one non-empty header are kept.
    """
    rows = set(header_rows)
    max_row = max(rows)
    per_col: dict[int, list[str]] = {}
    for r_idx, row in enumerate(
        worksheet.iter_rows(min_row=1, max_row=max_row, values_only=True), start=1
    ):
        if r_idx not in rows:
            continue
        for c_idx, val in enumerate(row, start=1):
            if val is not None and str(val).strip():
                per_col.setdefault(c_idx, []).append(str(val).strip())
    return {get_column_letter(c): " | ".join(parts) for c, parts in sorted(per_col.items())}


def extract_primary_headers(
    worksheet: Worksheet, *, row: int = PRIMARY_HEADER_ROW
) -> dict[str, str]:
    """Return each column's text from one row (default row 2, the primary header); {column letter: text}. For frontend display."""
    out: dict[str, str] = {}
    for r_idx, values in enumerate(
        worksheet.iter_rows(min_row=1, max_row=row, values_only=True), start=1
    ):
        if r_idx != row:
            continue
        for c_idx, val in enumerate(values, start=1):
            if val is not None and str(val).strip():
                out[get_column_letter(c_idx)] = str(val).strip()
    return out


# -----------------------------------------------------------------------------
# Fast path: is this header already the canonical template?
# -----------------------------------------------------------------------------
def headers_match_canonical(blobs: dict[str, str]) -> bool:
    """Decide whether this header is already the canonical layout (-> fast path, no Agent).

    Criterion: at each standard field's column position, the header blob must contain that
    field's canonical label. If any single core column doesn't match, the layout is deemed
    "changed" and we take the slow path.
    """
    for spec in STANDARD_FIELDS:
        blob = blobs.get(spec.column)
        if blob is None:
            return False
        norm_blob = _normalize(blob)
        if _normalize(spec.label) not in norm_blob:
            return False
    return True


# -----------------------------------------------------------------------------
# Deterministic matching backend (no API key; CI / offline / LLM fallback)
# -----------------------------------------------------------------------------
def _score_field(blob: str, spec: FieldSpec) -> float:
    """Score (column blob, standard field) in [0, 1]."""
    norm_blob = _normalize(blob)
    if not norm_blob:
        return 0.0

    candidates = [spec.label, spec.field.replace("_", " "), *spec.aliases]
    best = 0.0
    for cand in candidates:
        norm_cand = _normalize(cand)
        if not norm_cand:
            continue
        # Whole-string containment -> strong match
        if norm_cand in norm_blob or norm_blob in norm_cand:
            best = max(best, 0.97 if norm_cand == norm_blob else 0.92)
            continue
        # Token overlap (Jaccard)
        bt, ct = _tokens(blob), _tokens(cand)
        if bt and ct:
            overlap = len(bt & ct) / len(bt | ct)
            best = max(best, overlap)
    return round(best, 3)


def map_columns_deterministic(blobs: dict[str, str]) -> ColumnMapping:
    """Pure rule-based matching: each column picks its most similar standard field, with global dedup (one standard field per column)."""
    # Collect all (column, field, score)
    scored: list[tuple[str, FieldSpec, float]] = []
    for col, blob in blobs.items():
        for spec in STANDARD_FIELDS:
            score = _score_field(blob, spec)
            if score > 0:
                scored.append((col, spec, score))
    scored.sort(key=lambda x: x[2], reverse=True)

    taken_fields: set[str] = set()
    taken_cols: set[str] = set()
    chosen: dict[str, tuple[FieldSpec, float]] = {}
    for col, spec, score in scored:
        if col in taken_cols or spec.field in taken_fields:
            continue
        chosen[col] = (spec, score)
        taken_cols.add(col)
        taken_fields.add(spec.field)

    suggestions: list[ColumnSuggestion] = []
    for col, blob in blobs.items():
        if col in chosen:
            spec, score = chosen[col]
            suggestions.append(
                ColumnSuggestion(
                    excel_column=col,
                    excel_header=blob,
                    target_field=spec.field,
                    confidence=score,
                    reasoning=f"Deterministic match: header resembles field '{spec.field}' (canonical column {spec.column}), similarity {score}",
                )
            )
        else:
            suggestions.append(
                ColumnSuggestion(
                    excel_column=col,
                    excel_header=blob,
                    target_field=None,
                    confidence=0.0,
                    reasoning="No similar standard field",
                )
            )
    suggestions.sort(key=lambda s: _col_sort_key(s.excel_column))
    return ColumnMapping(suggestions=suggestions)


def _col_sort_key(letter: str) -> tuple[int, str]:
    return (len(letter), letter)


# -----------------------------------------------------------------------------
# LLM matching backend
# -----------------------------------------------------------------------------
def _build_llm_prompt(blobs: dict[str, str]) -> tuple[str, str]:
    field_lines = "\n".join(
        f"  - {spec.field} (canonical column {spec.column}): {spec.description}" for spec in STANDARD_FIELDS
    )
    system = (
        "You are the Schema-Mapping Agent for EcoTEA data onboarding.\n"
        "Given the header text of every column in a new Excel version, map each "
        "column to one of the 38 standard fields below with a confidence in [0, 1]. "
        "Headers may be renamed, reordered, or include unrelated extra columns.\n\n"
        f"Standard fields:\n{field_lines}\n\n"
        "Rules:\n"
        "1. target_field must be one of the standard field names, or null when no match.\n"
        "2. Each standard field may be claimed by at most one column (pick the best).\n"
        "3. confidence: exact synonym ~0.95+, clearly related ~0.7-0.9, weak ~0.4-0.6, "
        "unrelated -> 0 with target_field=null.\n"
        "4. reasoning: one short sentence (synonym, unit clue, ...).\n"
        "Output one suggestion for EVERY column.\n\n"
        "Examples (header -> match):\n"
        '  - "owner of data" -> data_owner (confidence ~0.95, synonym rewrite)\n'
        '  - "build cost" / "investment" / "NCAP_COST" -> capex (confidence ~0.9, '
        "NCAP_COST is the TIMES parameter for capital expenditure)\n"
        '  - "FO&M" -> fixed_opex (confidence ~0.9, Fixed O&M abbreviation)\n'
        '  - "Remarks for internal use" -> null (confidence 0, notes column matches nothing)'
    )
    col_lines = "\n".join(
        f"  Column {col}: {blob}"
        for col, blob in sorted(blobs.items(), key=lambda x: _col_sort_key(x[0]))
    )
    user = f"Column headers of the new Excel version:\n{col_lines}\n\nProduce the ColumnMapping."
    return system, user


def map_columns_llm(blobs: dict[str, str]) -> ColumnMapping:
    """Match via LLM structured output. Raises on failure; map_columns provides the fallback."""
    from langchain_core.messages import HumanMessage, SystemMessage

    from app.llm.provider import get_chat_model

    llm = get_chat_model()
    structured = llm.with_structured_output(ColumnMapping)
    system, user = _build_llm_prompt(blobs)
    mapping: ColumnMapping = structured.invoke(
        [SystemMessage(content=system), HumanMessage(content=user)]
    )
    # Sanitize: drop invalid target_field values
    for s in mapping.suggestions:
        if s.target_field is not None and s.target_field not in FIELD_BY_NAME:
            logger.warning("LLM returned unknown field %s, clearing it", s.target_field)
            s.target_field = None
            s.confidence = 0.0
    return mapping


def map_columns(blobs: dict[str, str], *, use_llm: bool = False) -> ColumnMapping:
    """Main entry point: pick a backend by use_llm; fall back to deterministic if the LLM fails."""
    if use_llm:
        try:
            return map_columns_llm(blobs)
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM column matching failed, falling back to the deterministic backend: %s", exc)
    return map_columns_deterministic(blobs)


# -----------------------------------------------------------------------------
# Relocation: mapping -> {source column -> canonical column}, then move a row's cells into canonical positions
# -----------------------------------------------------------------------------
def build_remap(
    mapping: ColumnMapping, *, min_confidence: float = AUTO_APPLY_THRESHOLD
) -> tuple[dict[str, str], list[ColumnSuggestion]]:
    """Split the match result into an "auto-applicable remap" and "low-confidence columns to review".

    Returns:
      remap: {source column -> canonical column}, only columns with confidence >= min_confidence
      needs_review: columns with REVIEW_THRESHOLD <= confidence < min_confidence
    Columns with confidence < REVIEW_THRESHOLD are dropped (treated as unmatched).
    """
    remap: dict[str, str] = {}
    needs_review: list[ColumnSuggestion] = []
    used_targets: set[str] = set()
    used_cols: set[str] = set()
    # Claim slots in descending confidence order: the deterministic backend already dedups
    # globally, but the LLM backend may return multiple columns pointing at the same target —
    # the higher-scoring column must win, not whichever appears first in the list.
    ordered = sorted(mapping.suggestions, key=lambda s: s.confidence, reverse=True)
    for s in ordered:
        if s.target_field is None or s.target_field not in FIELD_BY_NAME:
            continue
        target_col = FIELD_BY_NAME[s.target_field].column
        if s.confidence >= min_confidence:
            if target_col in used_targets or s.excel_column in used_cols:
                continue  # this canonical column / source column was already claimed by a higher score
            remap[s.excel_column] = target_col
            used_targets.add(target_col)
            used_cols.add(s.excel_column)
        elif s.confidence >= REVIEW_THRESHOLD:
            needs_review.append(s)
    needs_review.sort(key=lambda s: _col_sort_key(s.excel_column))
    return remap, needs_review


def validate_remap(
    remap: dict[str, str],
    needs_review: list[ColumnSuggestion],
    *,
    sheet_name: str = "",
) -> None:
    """Quality gate before auto-apply; raises SchemaMappingRejected when it doesn't pass.

    Used only on the Agent auto path; a user-confirmed override from preview skips this gate.
    """
    mapped_cols = set(remap.values())
    missing_core = [f for f in CORE_FIELDS if FIELD_BY_NAME[f].column not in mapped_cols]
    ratio = len(remap) / len(STANDARD_FIELDS)

    problems: list[str] = []
    if missing_core:
        problems.append(
            "core columns could not be auto-aligned: "
            + ", ".join(f"{f} (canonical column {FIELD_BY_NAME[f].column})" for f in missing_core)
        )
    if ratio < MIN_AUTO_MAPPED_RATIO:
        problems.append(
            f"auto-alignment coverage too low: {len(remap)}/{len(STANDARD_FIELDS)}"
            f" = {ratio:.0%} (threshold {MIN_AUTO_MAPPED_RATIO:.0%}); the column layout differs too much"
        )
    if problems:
        review_hint = (
            f"; {len(needs_review)} more column(s) fall in the review band" if needs_review else ""
        )
        raise SchemaMappingRejected(
            f"Automatic column alignment rejected for sheet '{sheet_name}': {'; '.join(problems)}"
            f"{review_hint}. Call POST /api/imports/preview to inspect the suggested mapping, "
            "then re-import with confirmed column_overrides."
        )


def remap_cells(cells: dict[str, object], remap: dict[str, str]) -> dict[str, object]:
    """Move a row's cells from source positions to canonical positions per remap.

    Columns not in remap are dropped (treated as unmatched; the importer naturally reads None).
    """
    return {std_col: cells.get(src_col) for src_col, std_col in remap.items()}


def describe_field(field_name: str) -> FieldSpec | None:
    return FIELD_BY_NAME.get(field_name)


__all__ = [
    "FieldSpec",
    "STANDARD_FIELDS",
    "STANDARD_FIELD_NAMES",
    "FIELD_BY_NAME",
    "FIELD_BY_COLUMN",
    "ColumnSuggestion",
    "ColumnMapping",
    "AUTO_APPLY_THRESHOLD",
    "REVIEW_THRESHOLD",
    "CORE_FIELDS",
    "MIN_AUTO_MAPPED_RATIO",
    "SchemaMappingRejected",
    "validate_remap",
    "extract_header_blobs",
    "extract_primary_headers",
    "headers_match_canonical",
    "map_columns",
    "map_columns_llm",
    "map_columns_deterministic",
    "build_remap",
    "remap_cells",
    "describe_field",
]
