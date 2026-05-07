"""
端到端逻辑验证脚本（无需 PostgreSQL）。

用一个 MockSession 替代真实 SQLAlchemy Session，捕获所有 db.add()/db.flush()/db.execute()
调用，统计各表会被插入多少条、内容是否合理。

用途：
  - 验证 import_excel() 在你修改逻辑后还能正确处理全部 38 列
  - 验证清洗规则（占位符 / #VALUE! / 混合文本 / 多商品）
  - 检查 sheet 名 vs A 列冲突时 sector 是否正确

运行：
  cd backend && python3 verify_import.py [/path/to/EcoTEA Endo WP1.xlsx]
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from itertools import count
from pathlib import Path
from typing import Any

# 让 app 包可被 import
sys.path.insert(0, str(Path(__file__).parent))

from app import models  # noqa: E402
from app.services import excel_importer  # noqa: E402

# -----------------------------------------------------------------------------
# Mock Session
# -----------------------------------------------------------------------------
_id_seq = count(1)


class MockResult:
    """模拟 db.execute(...) 的返回，目前只用于 ON CONFLICT INSERT。"""

    def fetchall(self):
        return []


class MockSession:
    """够用的 SQLAlchemy Session 替身。"""

    def __init__(self) -> None:
        self.inserts: dict[str, list[Any]] = defaultdict(list)
        self._lookup: dict[tuple[str, tuple], Any] = {}

    # ---- ORM 风格 ----
    def add(self, obj: Any) -> None:
        # 给 PK 字段填一个递增 id（如果未被设置）
        for pk_field in (
            "import_batch_id",
            "raw_row_id",
            "sector_id",
            "data_source_id",
            "geography_id",
            "commodity_id",
            "traceability_id",
            "technology_id",
            "technology_year_id",
            "technology_year_commodity_id",
            "constraint_id",
            "constraint_detail_id",
            "issue_id",
        ):
            if hasattr(obj, pk_field) and getattr(obj, pk_field) is None:
                setattr(obj, pk_field, next(_id_seq))
                break

        self.inserts[type(obj).__tablename__].append(obj)

        # 加进查找缓存（给 db.scalar(select(...)) 用）
        for keys in (
            ("sector_code",),
            ("geography_code",),
            ("commodity_code",),
            ("source_name", "source_description"),
            ("technology_code", "geography_id"),
            ("technology_id", "data_year"),
        ):
            if all(hasattr(obj, k) for k in keys):
                key_tuple = tuple(getattr(obj, k) for k in keys)
                self._lookup[(type(obj).__tablename__, key_tuple)] = obj

    def flush(self) -> None:
        pass

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass

    def close(self) -> None:
        pass

    # ---- 查询 ----
    def scalar(self, stmt: Any) -> Any:
        """模拟简单的 SELECT ... WHERE x = ? AND y = ?。"""
        # 解析 stmt：拿到 froms 和 where 子句
        try:
            froms = stmt.get_final_froms()
            table_name = froms[0].name
            criteria = self._extract_where_kvs(stmt)
        except Exception:
            return None

        # 查 lookup 缓存
        for keys in (
            ("sector_code",),
            ("geography_code",),
            ("commodity_code",),
            ("source_name", "source_description"),
            ("technology_code", "geography_id"),
            ("technology_id", "data_year"),
        ):
            if set(keys) == set(criteria.keys()):
                key_tuple = tuple(criteria[k] for k in keys)
                return self._lookup.get((table_name, key_tuple))

        return None

    def execute(self, _stmt: Any) -> MockResult:
        return MockResult()

    def scalars(self, stmt: Any) -> list[Any]:
        """模拟 db.scalars(...).all()。"""
        try:
            froms = stmt.get_final_froms()
            table_name = froms[0].name
            criteria = self._extract_where_kvs(stmt)
        except Exception:
            return []
        result = []
        for obj in self.inserts.get(table_name, []):
            if all(getattr(obj, k, None) == v for k, v in criteria.items()):
                result.append(obj)
        return result

    def get(self, model_cls: Any, pk: Any) -> Any:
        """模拟 db.get(Model, pk)。"""
        table = getattr(model_cls, "__tablename__", None)
        if table is None:
            return None
        # 在 inserts[table] 列表里按各种 pk 字段名查找
        for obj in self.inserts.get(table, []):
            for pk_field in (
                "import_batch_id",
                "raw_row_id",
                "sector_id",
                "data_source_id",
                "geography_id",
                "commodity_id",
                "traceability_id",
                "technology_id",
                "technology_year_id",
                "technology_year_commodity_id",
                "constraint_id",
                "constraint_detail_id",
                "issue_id",
            ):
                if hasattr(obj, pk_field) and getattr(obj, pk_field) == pk:
                    return obj
        return None

    @staticmethod
    def _extract_where_kvs(stmt: Any) -> dict[str, Any]:
        """从 select().where() 的 stmt 里抽出 {column_name: value}。"""
        kvs: dict[str, Any] = {}
        try:
            whereclause = stmt.whereclause
            if whereclause is None:
                return kvs
            clauses = (
                whereclause.clauses if hasattr(whereclause, "clauses") else [whereclause]
            )
            for clause in clauses:
                left = getattr(clause, "left", None)
                right = getattr(clause, "right", None)
                if left is not None and right is not None and hasattr(left, "name"):
                    val = getattr(right, "value", right)
                    kvs[left.name] = val
        except Exception:
            return {}
        return kvs


def _seed_sectors(session: MockSession) -> None:
    """模拟 schema.sql 里预置的 sector 行。"""
    seeds = [
        ("POWER", "Power"),
        ("INDUSTRY", "Industry"),
        ("PRIMARY", "Primary"),
        ("TRANSPORT", "Transport"),
        ("WATER", "Water"),
        ("WASTE", "Waste"),
        ("BUILDING", "Building"),
        ("HOUSEHOLD", "Household"),
        ("AGRI", "Agri"),
        ("INFOCOMM", "InfoComm"),
    ]
    for code, name in seeds:
        sector = models.Sector(sector_code=code, sector_name=name)
        sector.sector_id = next(_id_seq)
        session.inserts["sector"].append(sector)
        session._lookup[("sector", (code,))] = sector


# -----------------------------------------------------------------------------
# 主流程
# -----------------------------------------------------------------------------
def main(xlsx_path: Path, *, selected_sheets: list[str] | None = None) -> None:
    if not xlsx_path.exists():
        sys.exit(f"找不到 Excel 文件：{xlsx_path}")

    session = MockSession()
    _seed_sectors(session)

    file_bytes = xlsx_path.read_bytes()
    print(f"\n>>> 开始模拟导入：{xlsx_path.name}（{len(file_bytes):,} bytes）\n")

    # 顺便测试 preview 接口
    preview = excel_importer.preview_excel(
        file_bytes=file_bytes, file_name=xlsx_path.name
    )
    print("== 预览（preview_excel）==")
    print(f"  {'sheet':<12} {'known':>6} {'sector':>10} {'data_rows':>10}")
    for s in preview.sheets:
        print(
            f"  {s.sheet_name:<12} {('✓' if s.is_known else '✗'):>6} "
            f"{(s.sector_code or '-'):>10} {s.data_rows:>10}"
        )
    print()

    result = excel_importer.import_excel(
        session,
        file_bytes=file_bytes,
        file_name=xlsx_path.name,
        imported_by="verify_script",
        note="end-to-end logic check",
        selected_sheets=selected_sheets,
    )

    # ---- 整体摘要 ----
    print(f"== 总览 ==")
    print(f"  批次 id        : {result.import_batch_id}")
    print(f"  导入行数        : {result.rows_imported}")
    print(f"  跳过行数        : {result.rows_skipped}")
    print(f"  data_quality_issue : {result.issues}")
    print(f"  耗时           : {result.duration_ms} ms")
    print()

    # ---- 各 sheet 摘要 ----
    print(f"== 各 sheet 摘要 ==")
    print(
        f"  {'sheet':<12} {'rows_total':>10} {'imported':>10} {'skipped':>9} {'issues':>8}"
    )
    for s in result.sheets:
        print(
            f"  {s.sheet_name:<12} {s.rows_total:>10} "
            f"{s.rows_imported:>10} {s.rows_skipped:>9} {s.issues:>8}"
        )
    print()

    # ---- 各表插入数 ----
    print(f"== 各表插入条数 ==")
    table_order = [
        "import_batch",
        "raw_excel_row",
        "sector",
        "geography",
        "commodity",
        "traceability_record",
        "technology_process",
        "technology_year",
        "technology_year_ecotea_parameter",
        "technology_year_wp_descriptor",
        "technology_year_commodity",
        "technology_year_constraint",
        "technology_year_constraint_detail",
        "data_quality_issue",
    ]
    for tbl in table_order:
        cnt = len(session.inserts.get(tbl, []))
        marker = "✓" if cnt > 0 else "·"
        print(f"  {marker} {tbl:<40} {cnt:>6}")
    print()

    # ---- 抽样：多商品行 ----
    multi_commodity_groups = defaultdict(list)
    for tyc in session.inserts.get("technology_year_commodity", []):
        multi_commodity_groups[tyc.technology_year_id].append(tyc)
    multi = {k: v for k, v in multi_commodity_groups.items() if len(v) > 1}
    print(f"== 多商品组合行（应该有 PWRBMS+PWACOA 这类）：{len(multi)} 组 ==")
    commodity_by_id = {c.commodity_id: c for c in session.inserts.get("commodity", [])}
    for ty_id, items in list(multi.items())[:5]:
        codes = [
            commodity_by_id[it.commodity_id].commodity_code
            if it.commodity_id in commodity_by_id
            else f"id={it.commodity_id}"
            for it in items
        ]
        shares = [(it.commodity_share_value, it.commodity_share_text) for it in items]
        print(f"  technology_year_id={ty_id}: codes={codes} shares={shares}")
    print()

    # ---- 抽样：data_quality_issue ----
    issues_by_type = Counter(
        it.issue_type for it in session.inserts.get("data_quality_issue", [])
    )
    print(f"== data_quality_issue 类型分布 ==")
    for issue_type, cnt in issues_by_type.most_common():
        print(f"  {issue_type:<20} {cnt:>4}")
    print()

    # 列出前几条以便核对
    print(f"== data_quality_issue 抽样（前 5 条）==")
    for it in session.inserts.get("data_quality_issue", [])[:5]:
        print(
            f"  sheet={it.source_sheet_name} row={it.excel_row_number} "
            f"col={it.excel_column} type={it.issue_type} "
            f"orig={it.original_value!r}"
        )
    print()

    # ---- 抽样：sector 解决（特别检查 Agri 的 wp_title_raw='Building' 异常）----
    print(f"== Agri sheet 第 10 行（A 列 vs sheet 名冲突）==")
    for trace in session.inserts.get("traceability_record", []):
        if trace.source_sheet_name == "Agri" and trace.source_excel_row == 10:
            sector_obj = next(
                (
                    s
                    for s in session.inserts["sector"]
                    if s.sector_id == trace.sector_id
                ),
                None,
            )
            print(f"  wp_title_raw (A 列) = {trace.wp_title_raw!r}")
            print(f"  source_sheet_name   = {trace.source_sheet_name!r}")
            print(
                f"  sector_id           = {trace.sector_id} "
                f"({sector_obj.sector_code if sector_obj else '?'})"
            )
            print(
                "  → 期望 sector_code = AGRI（以 sheet 名为权威，wp_title_raw 仅审计）"
            )
            break

    # ---- 抽样：sector 冲突待复核 ----
    pending_rows = [
        r for r in session.inserts.get("raw_excel_row", [])
        if r.normalized_status == "pending_sector_review"
    ]
    print(f"\n== sector 冲突待复核（pending_sector_review）：{len(pending_rows)} 行 ==")
    for r in pending_rows[:3]:
        a_val = r.raw_cells.get("A") if r.raw_cells else None
        print(
            f"  raw_row_id={r.raw_row_id} sheet={r.source_sheet_name} "
            f"row={r.excel_row_number} A={a_val!r}"
        )

    # ---- 测试 list_pending_conflicts ----
    print(f"\n== list_pending_conflicts() ==")
    conflict_response = excel_importer.list_pending_conflicts(session)
    print(f"  total_pending = {conflict_response.total_pending}")
    print(f"  groups        = {len(conflict_response.groups)}")
    for g in conflict_response.groups[:3]:
        print(
            f"  - sheet={g.sheet_name} ({g.sheet_sector_code}) "
            f"vs A='{g.a_column_value}' ({g.a_column_sector_code}) — {len(g.rows)} 行"
        )

    # ---- 测试 resolve_pending_conflicts: TRUST_SHEET ----
    if pending_rows:
        from app.schemas import ConflictResolution
        resolutions = [
            ConflictResolution(raw_row_id=r.raw_row_id, decision="TRUST_SHEET")
            for r in pending_rows
        ]
        resolve_resp = excel_importer.resolve_pending_conflicts(
            session, resolutions=resolutions
        )
        print(f"\n== 提交 TRUST_SHEET 决定后 ==")
        print(f"  resolved={resolve_resp.resolved} failed={resolve_resp.failed}")

        # 再查一次 pending — 应该归零
        after = excel_importer.list_pending_conflicts(session)
        print(f"  剩余 pending = {after.total_pending}")

    print("\n>>> 完成。")


if __name__ == "__main__":
    xlsx = Path(
        sys.argv[1]
        if len(sys.argv) > 1
        else "/sessions/relaxed-beautiful-hamilton/mnt/uploads/EcoTEA Endo WP1.xlsx"
    )
    # 第二个参数：可选的 sheet 白名单（逗号分隔），用于验证「按 sheet 选择导入」
    selected: list[str] | None = None
    if len(sys.argv) > 2:
        selected = [s.strip() for s in sys.argv[2].split(",") if s.strip()]
        print(f"\n>>> 仅导入这些 sheet：{selected}\n")
    main(xlsx, selected_sheets=selected)
