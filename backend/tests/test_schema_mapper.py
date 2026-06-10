"""M5 Schema-Mapping Agent 测试。

分三层：
  * 单元：headers_match_canonical / map_columns（确定性）/ build_remap /
    remap_cells / validate_remap 质量门槛
  * LLM 后端：用 fake model 替身测清洗逻辑（非法字段置空）与失败回退确定性
  * 端到端：
      - 模板「整体右移一列」自动对齐导入
      - 「改名 + 右移」组合自动对齐导入
      - preview → column_overrides → import 人工复核回路
      - 大量改名 → SchemaMappingRejected 拒绝

无需 API key（LLM 路径用替身）。
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from openpyxl import load_workbook
from sqlalchemy import text

from app.agents import schema_mapper as sm
from tests._db_fixture import setup_test_db

TEMPLATE = (
    Path(__file__).resolve().parent.parent.parent / "uploads" / "template" / "EcoTEA Endo WP1.xlsx"
)
HAS_TEMPLATE = TEMPLATE.exists()


# -----------------------------------------------------------------------------
# 单元测试
# -----------------------------------------------------------------------------
def test_standard_field_count():
    # A..AL = 38 个标准字段，列位唯一
    assert len(sm.STANDARD_FIELDS) == 38
    cols = [f.column for f in sm.STANDARD_FIELDS]
    assert len(set(cols)) == 38


def test_deterministic_recovers_renamed_headers():
    blobs = {
        "B": "owner of data",  # data_owner
        "R": "build cost",  # capex
        "T": "FO&M charge",  # fixed_opex
        "O": "emissions factor",  # emission_factor
        "H": "asset name",  # technology_code
    }
    mapping = sm.map_columns(blobs, use_llm=False)
    got = {s.excel_column: s.target_field for s in mapping.suggestions}
    assert got["B"] == "data_owner"
    assert got["R"] == "capex"
    assert got["T"] == "fixed_opex"
    assert got["O"] == "emission_factor"
    assert got["H"] == "technology_code"


def test_one_field_one_column():
    # 两列都像 capex，只能有一列被判为 capex
    blobs = {"R": "capex", "S": "capex build cost"}
    mapping = sm.map_columns(blobs, use_llm=False)
    fields = [s.target_field for s in mapping.suggestions if s.target_field == "capex"]
    assert len(fields) == 1


def test_build_remap_thresholds():
    mapping = sm.ColumnMapping(
        suggestions=[
            sm.ColumnSuggestion(excel_column="F", target_field="capex", confidence=0.95),
            sm.ColumnSuggestion(excel_column="G", target_field="fixed_opex", confidence=0.75),
            sm.ColumnSuggestion(excel_column="X", target_field="heat_rate", confidence=0.3),
        ]
    )
    remap, review = sm.build_remap(mapping)
    assert remap == {"F": "R"}  # 高置信 → 搬到标准列 R
    assert [s.excel_column for s in review] == ["G"]  # 中置信 → 复核
    # 低置信 X 被丢弃


def test_remap_cells_moves_values():
    remap = {"F": "R", "G": "T"}
    cells = {"F": 100, "G": 50, "Z": "ignored"}
    out = sm.remap_cells(cells, remap)
    assert out == {"R": 100, "T": 50}


def test_build_remap_prefers_higher_confidence_on_duplicate_target():
    """LLM 后端可能返回两列指向同一标准字段——高分列必须赢，与列表顺序无关。"""
    mapping = sm.ColumnMapping(
        suggestions=[
            sm.ColumnSuggestion(excel_column="C", target_field="capex", confidence=0.91),
            sm.ColumnSuggestion(excel_column="F", target_field="capex", confidence=0.98),
        ]
    )
    remap, _ = sm.build_remap(mapping)
    assert remap == {"F": "R"}, "置信度 0.98 的 F 列应胜出，而非列表里先出现的 C 列"


def test_validate_remap_rejects_missing_core_fields():
    """核心列（technology_code/data_year）没对齐 → 拒绝。"""
    # 只对齐了 capex，核心列全缺
    remap = {"F": "R"}
    with pytest.raises(sm.SchemaMappingRejected) as exc_info:
        sm.validate_remap(remap, [], sheet_name="Power")
    msg = str(exc_info.value)
    assert "technology_code" in msg
    assert "preview" in msg  # 错误信息要指引用户走人工复核


def test_validate_remap_rejects_low_coverage():
    """核心列在但整体覆盖率低于门槛 → 拒绝。"""
    remap = {
        "H": sm.FIELD_BY_NAME["technology_code"].column,
        "K": sm.FIELD_BY_NAME["data_year"].column,
    }
    assert len(remap) / len(sm.STANDARD_FIELDS) < sm.MIN_AUTO_MAPPED_RATIO
    with pytest.raises(sm.SchemaMappingRejected, match="覆盖率"):
        sm.validate_remap(remap, [], sheet_name="Power")


def test_validate_remap_passes_good_mapping():
    """核心列齐 + 覆盖率达标 → 放行。"""
    remap = {spec.column: spec.column for spec in sm.STANDARD_FIELDS}
    sm.validate_remap(remap, [], sheet_name="Power")  # 不应抛


# -----------------------------------------------------------------------------
# LLM 后端（fake model 替身，无需 API key）
# -----------------------------------------------------------------------------
class _FakeStructuredLLM:
    """get_chat_model() 的替身：with_structured_output 后 invoke 返回预置结果。"""

    def __init__(self, result: sm.ColumnMapping):
        self._result = result
        self.invoked_with: list | None = None

    def with_structured_output(self, schema):  # noqa: ANN001
        assert schema is sm.ColumnMapping
        return self

    def invoke(self, messages):  # noqa: ANN001
        self.invoked_with = messages
        return self._result


def test_llm_backend_cleans_invalid_target_field(monkeypatch):
    """LLM 幻觉出不存在的字段名 → 置空并归零置信度。"""
    fake = _FakeStructuredLLM(
        sm.ColumnMapping(
            suggestions=[
                sm.ColumnSuggestion(
                    excel_column="A", target_field="hallucinated_field", confidence=0.99
                ),
                sm.ColumnSuggestion(excel_column="B", target_field="capex", confidence=0.95),
            ]
        )
    )
    import app.llm.provider as provider

    monkeypatch.setattr(provider, "get_chat_model", lambda **kw: fake)

    mapping = sm.map_columns_llm({"A": "mystery", "B": "build cost"})
    by_col = {s.excel_column: s for s in mapping.suggestions}
    assert by_col["A"].target_field is None
    assert by_col["A"].confidence == 0.0
    assert by_col["B"].target_field == "capex"
    # prompt 里应带 few-shot 与全部标准字段
    system_text = fake.invoked_with[0].content
    assert "owner of data" in system_text  # few-shot 示例
    assert "technology_code" in system_text


def test_llm_failure_falls_back_to_deterministic(monkeypatch):
    """LLM 后端抛异常 → map_columns 自动回退确定性后端。"""
    import app.llm.provider as provider

    def _boom(**kw):  # noqa: ANN003
        raise RuntimeError("no api key")

    monkeypatch.setattr(provider, "get_chat_model", _boom)
    mapping = sm.map_columns({"R": "build cost"}, use_llm=True)
    got = {s.excel_column: s.target_field for s in mapping.suggestions}
    assert got["R"] == "capex"


@pytest.mark.skipif(not HAS_TEMPLATE, reason="模板文件缺失")
def test_template_is_canonical():
    wb = load_workbook(TEMPLATE, data_only=True, read_only=True)
    blobs = sm.extract_header_blobs(wb["Power"])
    wb.close()
    assert sm.headers_match_canonical(blobs) is True


# -----------------------------------------------------------------------------
# 端到端：整体右移一列 → M5 自动对齐 → 导入
# -----------------------------------------------------------------------------
def _shift_template_right(only_sheet: str = "Power") -> bytes:
    """把模板某 sheet 整体右移一列（insert 一个空列在最前），其余 sheet 删掉。

    右移后标准列 R 的数据落在 S，mapper 必须把 S 重新对齐回 R。
    """
    wb = load_workbook(TEMPLATE, data_only=True)
    for name in list(wb.sheetnames):
        if name != only_sheet:
            del wb[name]
    wb[only_sheet].insert_cols(1)  # 所有列右移一格，A 变空
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.mark.skipif(not HAS_TEMPLATE, reason="模板文件缺失")
def test_end_to_end_shifted_import_aligns_columns():
    from app.database import SessionLocal
    from app.services.excel_importer import import_excel

    setup_test_db()

    shifted = _shift_template_right("Power")

    # 右移后的表头不再是标准布局
    wb = load_workbook(io.BytesIO(shifted), data_only=True, read_only=True)
    blobs = sm.extract_header_blobs(wb["Power"])
    wb.close()
    assert sm.headers_match_canonical(blobs) is False

    db = SessionLocal()
    try:
        result = import_excel(
            db,
            file_bytes=shifted,
            file_name="shifted.xlsx",
            note="m5-shift-test",
            auto_map_columns=True,
            use_llm_mapping=False,  # 确定性后端
        )
        assert result.rows_imported > 0, "右移文件经 M5 对齐后应能导入数据行"

        # 断言 capex 真落到了标准列（ecotea_parameter.capex 非空且为正）
        capex_rows = db.execute(
            text("SELECT COUNT(*) FROM technology_year_ecotea_parameter WHERE capex > 0")
        ).scalar()
        tech_codes = db.execute(
            text(
                "SELECT COUNT(*) FROM technology_process WHERE technology_code IS NOT NULL "
                "AND technology_code <> ''"
            )
        ).scalar()
    finally:
        db.close()

    assert capex_rows > 0, "capex 应被搬到标准列并写入"
    assert tech_codes > 0, "technology_code（H 列）应正确对齐"


# 常见改名（模拟 SG-TIMES 版本迭代），与 verify_schema_mapping.py 保持一致
RENAME = {
    "data owner": "owner of data",
    "capex": "build cost",
    "fixed opex": "FO&M charge",
    "variable opex": "VO&M",
    "ef": "emissions factor",
    "technology/process": "asset name",
    "year of data": "year",
}


def _rename_and_shift_template(only_sheet: str = "Power") -> bytes:
    """改名（row 2 换同义词）+ 整体右移一列：版本迭代的最坏常见组合。"""
    wb = load_workbook(TEMPLATE, data_only=True)
    for name in list(wb.sheetnames):
        if name != only_sheet:
            del wb[name]
    ws = wb[only_sheet]
    for cell in ws[2]:
        if cell.value and str(cell.value).lower() in RENAME:
            cell.value = RENAME[str(cell.value).lower()]
    ws.insert_cols(1)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.mark.skipif(not HAS_TEMPLATE, reason="模板文件缺失")
def test_end_to_end_renamed_and_shifted_import():
    """改名 + 换位组合：M5 自动对齐后导入，capex / 技术代码仍落到标准列。"""
    from app.database import SessionLocal
    from app.services.excel_importer import import_excel

    setup_test_db()
    db = SessionLocal()
    try:
        result = import_excel(
            db,
            file_bytes=_rename_and_shift_template("Power"),
            file_name="renamed_shifted.xlsx",
            note="m5-rename-shift-test",
            auto_map_columns=True,
            use_llm_mapping=False,
        )
        assert result.rows_imported > 0
        # ImportResult 必须暴露列对齐警告（启用了自动对齐）
        assert result.column_warnings, "启用 Schema-Mapping 时应有列级警告"
        assert any("Auto-aligned" in w for w in result.column_warnings)

        capex_rows = db.execute(
            text("SELECT COUNT(*) FROM technology_year_ecotea_parameter WHERE capex > 0")
        ).scalar()
    finally:
        db.close()
    assert capex_rows > 0, "改名+换位后 capex 仍应被搬到标准列"


@pytest.mark.skipif(not HAS_TEMPLATE, reason="模板文件缺失")
def test_preview_overrides_import_roundtrip():
    """人工复核回路：preview 给建议 → 组装 column_overrides → import 按它搬运。"""
    from app.database import SessionLocal
    from app.services.excel_importer import import_excel, preview_excel

    setup_test_db()
    shifted = _shift_template_right("Power")

    preview = preview_excel(file_bytes=shifted, file_name="shifted.xlsx")
    power = next(s for s in preview.sheets if s.sheet_name == "Power")
    assert power.column_mapping is not None
    assert power.column_mapping.layout_is_standard is False
    assert preview.standard_fields, "preview 应返回标准字段清单供前端下拉"

    # 模拟用户在 ColumnMappingReview 里全盘接受建议（auto + review 都确认）
    overrides = {
        s.excel_column: s.target_column
        for s in power.column_mapping.suggestions
        if s.target_column and s.status in ("auto", "review")
    }
    assert overrides, "右移文件应有可确认的列建议"

    db = SessionLocal()
    try:
        result = import_excel(
            db,
            file_bytes=shifted,
            file_name="shifted.xlsx",
            note="m5-overrides-roundtrip",
            column_overrides={"Power": overrides},
            auto_map_columns=False,  # 有 override 时不再调 Agent
        )
        assert result.rows_imported > 0
        capex_rows = db.execute(
            text("SELECT COUNT(*) FROM technology_year_ecotea_parameter WHERE capex > 0")
        ).scalar()
    finally:
        db.close()
    assert capex_rows > 0, "用户确认的 overrides 应被原样应用"


@pytest.mark.skipif(not HAS_TEMPLATE, reason="模板文件缺失")
def test_end_to_end_garbled_headers_rejected():
    """大量改名（表头面目全非）→ 拒绝导入并提示，而不是静默产出残缺数据。"""
    from app.database import SessionLocal
    from app.services.excel_importer import import_excel

    setup_test_db()
    wb = load_workbook(TEMPLATE, data_only=True)
    for name in list(wb.sheetnames):
        if name != "Power":
            del wb[name]
    ws = wb["Power"]
    # 把 1-9 行所有表头改成无意义占位，核心列信号全毁
    for row in ws.iter_rows(min_row=1, max_row=9):
        for cell in row:
            if cell.value is not None:
                cell.value = f"mystery_{cell.column_letter}_{cell.row}"
    buf = io.BytesIO()
    wb.save(buf)

    db = SessionLocal()
    try:
        with pytest.raises(sm.SchemaMappingRejected, match="technology_code"):
            import_excel(
                db,
                file_bytes=buf.getvalue(),
                file_name="garbled.xlsx",
                auto_map_columns=True,
                use_llm_mapping=False,
            )
    finally:
        db.close()


@pytest.mark.skipif(not HAS_TEMPLATE, reason="模板文件缺失")
def test_standard_template_still_imports_fast_path():
    """回归：标准模板仍走快路径（column_remap=None），导入不受 M5 影响。"""
    from app.database import SessionLocal
    from app.services.excel_importer import import_excel

    setup_test_db()
    wb = load_workbook(TEMPLATE, data_only=True)
    for name in list(wb.sheetnames):
        if name != "Power":
            del wb[name]
    buf = io.BytesIO()
    wb.save(buf)

    db = SessionLocal()
    try:
        result = import_excel(
            db,
            file_bytes=buf.getvalue(),
            file_name="std.xlsx",
            auto_map_columns=True,
            use_llm_mapping=False,
        )
        assert result.rows_imported > 0
    finally:
        db.close()
