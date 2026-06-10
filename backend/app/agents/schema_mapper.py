"""Schema-Mapping Agent（M5）— 自动对齐 SG-TIMES 版本迭代的列布局变化。

定位（与 M3 的查询四 Agent 解耦）：
  * M3 的 Planner→SQL→Interpreter→Visualizer 是 **查询时** 的 LangGraph 链路。
  * 本模块是 **数据接入时** 的独立 Agent，不在那张图里，单独被导入流程调用。

要解决的问题：
  现有 excel_importer 把列位置写死（capex 永远在 R 列、ef 在 O 列……），
  默认输入 Excel 和标准模板列布局完全一致。一旦 SG-TIMES 换版本——列改名 /
  换位 / 增删列——R 列就不再是 capex，导入会静默错位。

本模块的职责正是补这个缺口：
  给定一个陌生 Excel 的表头，产出映射 `{陌生列 -> 标准列}`，让“搬运”之后
  importer 的硬编码 `field_to_column` 依然成立。importer 一行不改。

两条路：
  1. 快路径：表头和标准模板一致 → headers_match_canonical() 返回 True →
     不调 LLM，直接走原硬编码导入（日常 99% 情况，零成本）。
  2. 慢路径：表头对不上 → map_columns() 语义匹配 → 每列给置信度：
       confidence ≥ 0.9        自动应用
       0.6 ≤ confidence < 0.9   交人工复核（写 data_quality_issue / 前端列对齐）
       confidence < 0.6        当未匹配，置 NULL

匹配实现有两种后端，靠 `use_llm` 切换：
  * LLM 后端：llm.with_structured_output(ColumnMapping)，强类型、防幻觉字段。
  * 确定性后端：纯 token/别名匹配，**无需 API key**，供 CI / 离线 / LLM 失败兜底。
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

# 表头所在行：模板 row 2 是最易读的主表头，row 1/3-9 是 WP 各层补充别名。
# 做语义匹配时把 1-9 行同列文本拼成一个 “表头 blob”，给匹配器最大信号量。
HEADER_ROW_RANGE = range(1, 10)
PRIMARY_HEADER_ROW = 2


# -----------------------------------------------------------------------------
# 标准字段表（单一事实来源）
#   column 就是 importer 里硬编码的标准列位；label 是模板 row 2 的人类表头；
#   aliases 覆盖 SG-TIMES 各 WP 层 / 常见同义改名。
# -----------------------------------------------------------------------------
@dataclass(frozen=True)
class FieldSpec:
    field: str  # 标准字段名（业务语义）
    column: str  # 标准列位（Excel 列字母，importer 硬编码的那个）
    label: str  # 模板主表头（row 2）
    description: str  # 给 LLM 的字段说明
    aliases: tuple[str, ...] = dc_field(default_factory=tuple)


STANDARD_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(
        "wp_title",
        "A",
        "WP6 Title",
        "工作包标题 / 所属部门标签（也是 sector 文本来源）",
        ("wp title", "wp6 title", "sector", "work package", "title"),
    ),
    FieldSpec(
        "data_owner", "B", "data owner", "数据所有者", ("owner", "owner of data", "data owner")
    ),
    FieldSpec(
        "data_provider",
        "C",
        "data provider",
        "数据提供方",
        ("provider", "data provider", "source provider"),
    ),
    FieldSpec(
        "data_source",
        "D",
        "data source",
        "数据来源 / 模型运行名",
        ("source", "data source", "model run name", "dataset"),
    ),
    FieldSpec(
        "data_source_description",
        "E",
        "data source description",
        "数据来源描述",
        ("source description", "data source desc", "source desc"),
    ),
    FieldSpec("data_user", "F", "data user", "数据使用方", ("user", "data user")),
    FieldSpec(
        "usage_purpose", "G", "usage purpose", "使用目的", ("purpose", "usage", "usage purpose")
    ),
    FieldSpec(
        "technology_code",
        "H",
        "technology/process",
        "技术 / 工艺代码（anchor 主键）",
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
        "技术 / 工艺描述",
        ("technology description", "process description", "asset description", "tech desc"),
    ),
    FieldSpec(
        "geography",
        "J",
        "Geography",
        "地理 / 国家 / 区域",
        ("geography", "country", "region", "geo"),
    ),
    FieldSpec(
        "data_year",
        "K",
        "year of data",
        "数据年份（anchor 的时间维）",
        ("year", "year of data", "data year"),
    ),
    FieldSpec(
        "technology_start_year",
        "L",
        "Technology Start Year",
        "技术最早建设 / 起始年",
        ("start year", "technology start year", "earliest build year", "ncap_start"),
    ),
    FieldSpec(
        "technology_lifetime_years",
        "M",
        "technology lifetime (years)",
        "技术寿命（年）",
        ("lifetime", "technology lifetime", "tlife", "ncap_tlife"),
    ),
    FieldSpec("grade", "N", "Grade", "等级 / 分级", ("grade",)),
    FieldSpec(
        "emission_factor",
        "O",
        "ef",
        "排放因子",
        ("ef", "emission factor", "emissions factor", "vda_emcb", "emcb"),
    ),
    FieldSpec(
        "emission_factor_unit",
        "P",
        "ef ref unit",
        "排放因子参考单位",
        ("ef unit", "ef ref unit", "emission factor unit"),
    ),
    FieldSpec(
        "base_currency",
        "Q",
        "base currency",
        "基准货币（分子）",
        ("currency", "base currency", "numerator currency"),
    ),
    FieldSpec(
        "capex",
        "R",
        "capex",
        "资本支出",
        ("capex", "build cost", "investment", "capital cost", "ncap_cost", "capital expenditure"),
    ),
    FieldSpec(
        "capex_unit",
        "S",
        "capex ref unit",
        "capex 参考单位（分母）",
        ("capex unit", "capex ref unit", "capacity unit"),
    ),
    FieldSpec(
        "fixed_opex",
        "T",
        "fixed opex",
        "固定运维成本",
        ("fixed opex", "fom", "fo&m", "fixed o&m", "ncap_fom", "fixed operating cost"),
    ),
    FieldSpec(
        "fixed_opex_unit",
        "U",
        "fixed opex ref unit",
        "固定运维参考单位",
        ("fixed opex unit", "fom unit", "fixed opex ref unit"),
    ),
    FieldSpec(
        "variable_opex",
        "V",
        "variable opex",
        "可变运维成本",
        ("variable opex", "vom", "vo&m", "act_cost", "variable operating cost"),
    ),
    FieldSpec(
        "variable_opex_unit",
        "W",
        "variable opex ref unit",
        "可变运维参考单位",
        ("variable opex unit", "vom unit", "variable opex ref unit", "activity unit"),
    ),
    FieldSpec("tax_cost", "X", "Tax cost", "税成本", ("tax", "tax cost")),
    FieldSpec("subsidy_cost", "Y", "Sub cost", "补贴成本", ("subsidy", "sub cost", "subsidy cost")),
    FieldSpec(
        "efficiency", "Z", "efficiency", "效率（WP 特定技术描述）", ("efficiency", "act_eff", "eff")
    ),
    FieldSpec(
        "technology_efficiency",
        "AA",
        "technology efficiency",
        "技术效率",
        ("technology efficiency", "tech efficiency"),
    ),
    FieldSpec(
        "commodity_share",
        "AB",
        "commodity share",
        "商品份额",
        ("commodity share", "flo_share", "share", "by energy use"),
    ),
    FieldSpec(
        "commodity_code", "AC", "commodity", "商品代码", ("commodity", "commodity code", "fuel")
    ),
    FieldSpec(
        "commodity_demand", "AD", "Commodity Demand", "商品需求量", ("commodity demand", "demand")
    ),
    FieldSpec(
        "interpolation_rule",
        "AE",
        "Interpolation rule",
        "插值规则",
        ("interpolation rule", "interpolation", "interp rule"),
    ),
    FieldSpec(
        "capacity_to_activity_factor",
        "AF",
        "capacity to activity factor",
        "容量到活动转换系数",
        ("capacity to activity factor", "afa", "c2a"),
    ),
    FieldSpec("heat_rate", "AG", "heat rate", "热耗率", ("heat rate", "heatrate")),
    FieldSpec(
        "capacity",
        "AH",
        "capacity",
        "容量约束值",
        ("capacity", "wp1 constraints", "capacity constraint"),
    ),
    FieldSpec(
        "bound_type",
        "AI",
        "capacity type",
        "容量约束类型（fixed/up/lo）",
        ("capacity type", "bound type", "capacity constraint type"),
    ),
    FieldSpec(
        "max_import_possible",
        "AJ",
        "max import possible",
        "最大可进口量",
        ("max import possible", "act_bnd", "max import"),
    ),
    FieldSpec(
        "max_solar_output_allowed",
        "AK",
        "max solar output allowed",
        "最大允许太阳能出力",
        ("max solar output allowed", "uc_rhsrt", "max solar output"),
    ),
    # 注意：label 必须与模板 row 2 原文一致（headers_match_canonical 依赖它），
    # 模板里 AH / AL 的 row 2 都是 "capacity"，靠 aliases / description 区分语义。
    # "uc_rhsrt" 别名只留给 AK（其 blob 还有 "max solar output allowed" 强信号），
    # 避免 AK / AL 两列在确定性匹配里抢同一个别名。
    FieldSpec(
        "capacity_special",
        "AL",
        "capacity",
        "特殊容量约束（UC 约束右端项 UC_RHSRT，区别于 AH 的常规容量约束）",
        ("capacity special", "special capacity", "uc capacity"),
    ),
)

# 索引
FIELD_BY_NAME: dict[str, FieldSpec] = {f.field: f for f in STANDARD_FIELDS}
FIELD_BY_COLUMN: dict[str, FieldSpec] = {f.column: f for f in STANDARD_FIELDS}
STANDARD_FIELD_NAMES: tuple[str, ...] = tuple(f.field for f in STANDARD_FIELDS)


# -----------------------------------------------------------------------------
# 结构化输出 schema（LLM 用 with_structured_output 强约束）
# -----------------------------------------------------------------------------
class ColumnSuggestion(BaseModel):
    """单列的匹配结果。"""

    excel_column: str = Field(..., description="陌生 Excel 的列字母，如 'A'/'B'/'AB'")
    excel_header: str = Field(default="", description="该列表头原文")
    target_field: str | None = Field(
        default=None,
        description="匹配到的标准字段名（STANDARD_FIELD_NAMES 之一）；无法匹配填 null",
    )
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="0-1 置信度")
    reasoning: str = Field(default="", description="匹配理由（简短）")


class ColumnMapping(BaseModel):
    """整张 sheet 的列匹配结果。"""

    suggestions: list[ColumnSuggestion] = Field(default_factory=list)


# 置信度阈值（与 PlanReadme M5 一致）
AUTO_APPLY_THRESHOLD = 0.9
REVIEW_THRESHOLD = 0.6

# 自动应用的质量门槛（“大量改名 → 拒绝并提示”三档验收的第三档）
#   - 核心列：anchor 主键来源，缺了导入只会产出空数据或脏数据
#   - 覆盖率：自动对齐列数 / 标准字段数 低于此值说明布局变化太大，不可盲导
CORE_FIELDS: tuple[str, ...] = ("technology_code", "data_year")
MIN_AUTO_MAPPED_RATIO = 0.5


class SchemaMappingRejected(ValueError):  # noqa: N818 - public API name kept stable
    """自动列对齐质量不达标，拒绝静默导入。

    由导入流程捕获并转成 4xx，提示用户走 preview 的列对齐复核（人工 override）。
    """


# -----------------------------------------------------------------------------
# 表头读取 & 规范化
# -----------------------------------------------------------------------------
def _normalize(text: object) -> str:
    """小写、去标点、压空白，用于鲁棒比较。"""
    s = str(text or "").lower()
    s = re.sub(r"[^a-z0-9一-鿿]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _tokens(text: str) -> set[str]:
    return {t for t in _normalize(text).split() if t}


def extract_header_blobs(
    worksheet: Worksheet, *, header_rows: Iterable[int] = HEADER_ROW_RANGE
) -> dict[str, str]:
    """逐列把表头行（1-9）的非空文本拼成一个 blob，返回 {列字母: blob}。

    用 iter_rows 实现，read_only / 普通模式都适用。
    只保留至少有一处非空表头的列。
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
    """取某一行（默认 row 2 主表头）每列原文，返回 {列字母: 文本}。前端展示用。"""
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
# 快路径：表头是否就是标准模板
# -----------------------------------------------------------------------------
def headers_match_canonical(blobs: dict[str, str]) -> bool:
    """判断这张表头是否已是标准布局（→ 走快路径，不调 Agent）。

    判据：每个标准字段的列位上，表头 blob 必须包含该字段的标准 label。
    只要有一个核心列对不上，就判为“布局变了”，走慢路径。
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
# 确定性匹配后端（无需 API key；CI / 离线 / LLM 兜底）
# -----------------------------------------------------------------------------
def _score_field(blob: str, spec: FieldSpec) -> float:
    """给 (列 blob, 标准字段) 打 0-1 相似分。"""
    norm_blob = _normalize(blob)
    if not norm_blob:
        return 0.0

    candidates = [spec.label, spec.field.replace("_", " "), *spec.aliases]
    best = 0.0
    for cand in candidates:
        norm_cand = _normalize(cand)
        if not norm_cand:
            continue
        # 整串包含 → 强匹配
        if norm_cand in norm_blob or norm_blob in norm_cand:
            best = max(best, 0.97 if norm_cand == norm_blob else 0.92)
            continue
        # token 重叠（Jaccard）
        bt, ct = _tokens(blob), _tokens(cand)
        if bt and ct:
            overlap = len(bt & ct) / len(bt | ct)
            best = max(best, overlap)
    return round(best, 3)


def map_columns_deterministic(blobs: dict[str, str]) -> ColumnMapping:
    """纯规则匹配：每列挑最相似的标准字段，做全局去重（一个标准字段只给一列）。"""
    # 收集所有 (列, 字段, 分数)
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
                    reasoning=f"确定性匹配：表头与字段 '{spec.field}'（标准列 {spec.column}）相似度 {score}",
                )
            )
        else:
            suggestions.append(
                ColumnSuggestion(
                    excel_column=col,
                    excel_header=blob,
                    target_field=None,
                    confidence=0.0,
                    reasoning="无相似标准字段",
                )
            )
    suggestions.sort(key=lambda s: _col_sort_key(s.excel_column))
    return ColumnMapping(suggestions=suggestions)


def _col_sort_key(letter: str) -> tuple[int, str]:
    return (len(letter), letter)


# -----------------------------------------------------------------------------
# LLM 匹配后端
# -----------------------------------------------------------------------------
def _build_llm_prompt(blobs: dict[str, str]) -> tuple[str, str]:
    field_lines = "\n".join(
        f"  - {spec.field}（标准列 {spec.column}）：{spec.description}" for spec in STANDARD_FIELDS
    )
    system = (
        "你是 SG-TIMES 数据接入的 Schema-Mapping Agent。\n"
        "给你一张新版 Excel 每一列的表头文本，你要把每列匹配到下面 38 个标准字段之一，"
        "并给出 0-1 的置信度。表头可能改名、换位、或多了无关列。\n\n"
        f"标准字段清单：\n{field_lines}\n\n"
        "规则：\n"
        "1. target_field 只能取上面的标准字段名，或在无法匹配时填 null。\n"
        "2. 一个标准字段最多匹配一列（择优）。\n"
        "3. confidence：完全同义≈0.95+，明显相关≈0.7-0.9，勉强≈0.4-0.6，无关填 0 且 target_field=null。\n"
        "4. reasoning 用一句话说明依据（比如同义词、单位线索）。\n"
        "对每一列都要输出一条 suggestion。\n\n"
        "示例（表头 → 匹配）：\n"
        '  - "owner of data" → data_owner（confidence≈0.95，同义改写）\n'
        '  - "build cost" / "investment" / "NCAP_COST" → capex（confidence≈0.9，'
        "TIMES 参数名 NCAP_COST 即资本支出）\n"
        '  - "FO&M" → fixed_opex（confidence≈0.9，Fixed O&M 缩写）\n'
        '  - "Remarks for internal use" → null（confidence=0，备注列与任何标准字段无关）'
    )
    col_lines = "\n".join(
        f"  列 {col}：{blob}"
        for col, blob in sorted(blobs.items(), key=lambda x: _col_sort_key(x[0]))
    )
    user = f"新版 Excel 的列表头如下：\n{col_lines}\n\n请输出 ColumnMapping。"
    return system, user


def map_columns_llm(blobs: dict[str, str]) -> ColumnMapping:
    """用 LLM 结构化输出做匹配。失败时抛异常，由 map_columns 兜底。"""
    from langchain_core.messages import HumanMessage, SystemMessage

    from app.llm.provider import get_chat_model

    llm = get_chat_model()
    structured = llm.with_structured_output(ColumnMapping)
    system, user = _build_llm_prompt(blobs)
    mapping: ColumnMapping = structured.invoke(
        [SystemMessage(content=system), HumanMessage(content=user)]
    )
    # 清洗：丢弃非法 target_field
    for s in mapping.suggestions:
        if s.target_field is not None and s.target_field not in FIELD_BY_NAME:
            logger.warning("LLM 返回未知字段 %s，置空", s.target_field)
            s.target_field = None
            s.confidence = 0.0
    return mapping


def map_columns(blobs: dict[str, str], *, use_llm: bool = False) -> ColumnMapping:
    """对外主入口：根据 use_llm 选后端，LLM 失败自动回退确定性。"""
    if use_llm:
        try:
            return map_columns_llm(blobs)
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM 列匹配失败，回退确定性后端：%s", exc)
    return map_columns_deterministic(blobs)


# -----------------------------------------------------------------------------
# 搬运：映射 -> {陌生列 -> 标准列}，再把行 cells 搬到标准列位
# -----------------------------------------------------------------------------
def build_remap(
    mapping: ColumnMapping, *, min_confidence: float = AUTO_APPLY_THRESHOLD
) -> tuple[dict[str, str], list[ColumnSuggestion]]:
    """把匹配结果拆成「可自动应用的 remap」和「待人工复核的低置信列」。

    返回:
      remap: {陌生列 -> 标准列}，只含 confidence >= min_confidence 的列
      needs_review: REVIEW_THRESHOLD <= confidence < min_confidence 的列
    confidence < REVIEW_THRESHOLD 的列被丢弃（当未匹配）。
    """
    remap: dict[str, str] = {}
    needs_review: list[ColumnSuggestion] = []
    used_targets: set[str] = set()
    used_cols: set[str] = set()
    # 按置信度降序占坑：确定性后端已全局去重，但 LLM 后端可能返回
    # 多列指向同一 target——必须保证高分列赢，而不是列表里先出现的赢。
    ordered = sorted(mapping.suggestions, key=lambda s: s.confidence, reverse=True)
    for s in ordered:
        if s.target_field is None or s.target_field not in FIELD_BY_NAME:
            continue
        target_col = FIELD_BY_NAME[s.target_field].column
        if s.confidence >= min_confidence:
            if target_col in used_targets or s.excel_column in used_cols:
                continue  # 同一标准列 / 源列已被更高分占用
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
    """自动应用前的质量门槛，不达标抛 SchemaMappingRejected。

    只用于 Agent 自动路径；用户在 preview 里人工确认的 override 不走此门槛。
    """
    mapped_cols = set(remap.values())
    missing_core = [f for f in CORE_FIELDS if FIELD_BY_NAME[f].column not in mapped_cols]
    ratio = len(remap) / len(STANDARD_FIELDS)

    problems: list[str] = []
    if missing_core:
        problems.append(
            "核心列未能自动对齐："
            + ", ".join(f"{f}（标准列 {FIELD_BY_NAME[f].column}）" for f in missing_core)
        )
    if ratio < MIN_AUTO_MAPPED_RATIO:
        problems.append(
            f"自动对齐覆盖率过低：{len(remap)}/{len(STANDARD_FIELDS)}"
            f" = {ratio:.0%}（门槛 {MIN_AUTO_MAPPED_RATIO:.0%}），列布局变化太大"
        )
    if problems:
        review_hint = f"；另有 {len(needs_review)} 列置信度在复核区间" if needs_review else ""
        raise SchemaMappingRejected(
            f"sheet '{sheet_name}' 列布局自动对齐被拒绝：{'；'.join(problems)}"
            f"{review_hint}。请先调用 POST /api/imports/preview 查看列对齐建议，"
            "人工确认后通过 column_overrides 重新导入。"
        )


def remap_cells(cells: dict[str, object], remap: dict[str, str]) -> dict[str, object]:
    """按 remap 把一行 cells 从陌生列位搬到标准列位。

    未在 remap 里的列被丢弃（视为未匹配，importer 自然读到 None）。
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
