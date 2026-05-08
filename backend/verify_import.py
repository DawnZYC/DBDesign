"""
End-to-end logic verification script without PostgreSQL.

Uses MockSession instead of a real SQLAlchemy Session, captures all db.add() /
db.flush() / db.execute() calls, and reports insert counts and sample content.

Purpose:
  - Verify import_excel() still handles all 38 columns after logic changes.
  - Verify cleaning rules for placeholders / #VALUE! / mixed text / multi-commodity rows.
  - Check sector behavior when sheet name conflicts with column A.

Run:
  cd backend && python3 verify_import.py [/path/to/EcoTEA Endo WP1.xlsx]
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from itertools import count
from pathlib import Path
from typing import Any

# Make the app package importable.
sys.path.insert(0, str(Path(__file__).parent))

from app import models  # noqa: E402
from app.services import excel_importer  # noqa: E402

# -----------------------------------------------------------------------------
# Mock Session
# -----------------------------------------------------------------------------
_id_seq = count(1)


class MockResult:
    """Mock return value for db.execute(...), currently only used for ON CONFLICT INSERT."""

    def fetchall(self):
        return []


class MockSession:
    """Minimal SQLAlchemy Session substitute."""

    def __init__(self) -> None:
        self.inserts: dict[str, list[Any]] = defaultdict(list)
        self._lookup: dict[tuple[str, tuple], Any] = {}

    # ---- ORM style ----
    def add(self, obj: Any) -> None:
        # Fill a primary key field with an incrementing ID if it is unset.
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

        # Add to lookup cache for db.scalar(select(...)).
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

    # ---- Queries ----
    def scalar(self, stmt: Any) -> Any:
        """Mock a simple SELECT ... WHERE x = ? AND y = ?."""
        # Parse stmt to obtain froms and where clauses.
        try:
            froms = stmt.get_final_froms()
            table_name = froms[0].name
            criteria = self._extract_where_kvs(stmt)
        except Exception:
            return None

        # Check lookup cache.
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
        """Mock db.scalars(...).all()."""
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
        """Mock db.get(Model, pk)."""
        table = getattr(model_cls, "__tablename__", None)
        if table is None:
            return None
        # Look up objects in inserts[table] by known primary key field names.
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
        """Extract {column_name: value} from a select().where() statement."""
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
    """Mock the sector rows seeded by schema.sql."""
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
# Main flow
# -----------------------------------------------------------------------------
def main(xlsx_path: Path, *, selected_sheets: list[str] | None = None) -> None:
    if not xlsx_path.exists():
        sys.exit(f"Excel file not found: {xlsx_path}")

    session = MockSession()
    _seed_sectors(session)

    file_bytes = xlsx_path.read_bytes()
    print(f"\n>>> Starting simulated import: {xlsx_path.name} ({len(file_bytes):,} bytes)\n")

    # Also test the preview interface.
    preview = excel_importer.preview_excel(
        file_bytes=file_bytes, file_name=xlsx_path.name
    )
    print("== Preview (preview_excel) ==")
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

    # ---- Overall summary ----
    print("== Overview ==")
    print(f"  batch id        : {result.import_batch_id}")
    print(f"  imported rows   : {result.rows_imported}")
    print(f"  skipped rows    : {result.rows_skipped}")
    print(f"  data_quality_issue : {result.issues}")
    print(f"  duration        : {result.duration_ms} ms")
    print()

    # ---- Per-sheet summary ----
    print("== Per-sheet Summary ==")
    print(
        f"  {'sheet':<12} {'rows_total':>10} {'imported':>10} {'skipped':>9} {'issues':>8}"
    )
    for s in result.sheets:
        print(
            f"  {s.sheet_name:<12} {s.rows_total:>10} "
            f"{s.rows_imported:>10} {s.rows_skipped:>9} {s.issues:>8}"
        )
    print()

    # ---- Insert counts by table ----
    print("== Insert Counts by Table ==")
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

    # ---- Sample: multi-commodity rows ----
    multi_commodity_groups = defaultdict(list)
    for tyc in session.inserts.get("technology_year_commodity", []):
        multi_commodity_groups[tyc.technology_year_id].append(tyc)
    multi = {k: v for k, v in multi_commodity_groups.items() if len(v) > 1}
    print(f"== Multi-commodity rows, such as PWRBMS+PWACOA: {len(multi)} groups ==")
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

    # ---- Sample: data_quality_issue ----
    issues_by_type = Counter(
        it.issue_type for it in session.inserts.get("data_quality_issue", [])
    )
    print("== data_quality_issue Type Distribution ==")
    for issue_type, cnt in issues_by_type.most_common():
        print(f"  {issue_type:<20} {cnt:>4}")
    print()

    # Print the first few rows for checking.
    print("== data_quality_issue Sample (first 5 rows) ==")
    for it in session.inserts.get("data_quality_issue", [])[:5]:
        print(
            f"  sheet={it.source_sheet_name} row={it.excel_row_number} "
            f"col={it.excel_column} type={it.issue_type} "
            f"orig={it.original_value!r}"
        )
    print()

    # ---- Sample: sector resolution, especially Agri row 10 with wp_title_raw='Building'. ----
    print("== Agri sheet row 10 (column A vs sheet name conflict) ==")
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
            print(f"  wp_title_raw (column A) = {trace.wp_title_raw!r}")
            print(f"  source_sheet_name   = {trace.source_sheet_name!r}")
            print(
                f"  sector_id           = {trace.sector_id} "
                f"({sector_obj.sector_code if sector_obj else '?'})"
            )
            print(
                "  -> expected sector_code = AGRI; sheet name is authoritative and wp_title_raw is audit-only"
            )
            break

    # ---- Sample: sector conflicts pending review ----
    pending_rows = [
        r for r in session.inserts.get("raw_excel_row", [])
        if r.normalized_status == "pending_sector_review"
    ]
    print(f"\n== Sector Conflicts Pending Review (pending_sector_review): {len(pending_rows)} rows ==")
    for r in pending_rows[:3]:
        a_val = r.raw_cells.get("A") if r.raw_cells else None
        print(
            f"  raw_row_id={r.raw_row_id} sheet={r.source_sheet_name} "
            f"row={r.excel_row_number} A={a_val!r}"
        )

    # ---- Test list_pending_conflicts ----
    print(f"\n== list_pending_conflicts() ==")
    conflict_response = excel_importer.list_pending_conflicts(session)
    print(f"  total_pending = {conflict_response.total_pending}")
    print(f"  groups        = {len(conflict_response.groups)}")
    for g in conflict_response.groups[:3]:
        print(
            f"  - sheet={g.sheet_name} ({g.sheet_sector_code}) "
            f"vs A='{g.a_column_value}' ({g.a_column_sector_code}) - {len(g.rows)} rows"
        )

    # ---- Test resolve_pending_conflicts: TRUST_SHEET ----
    if pending_rows:
        from app.schemas import ConflictResolution
        resolutions = [
            ConflictResolution(raw_row_id=r.raw_row_id, decision="TRUST_SHEET")
            for r in pending_rows
        ]
        resolve_resp = excel_importer.resolve_pending_conflicts(
            session, resolutions=resolutions
        )
        print("\n== After Submitting TRUST_SHEET Decisions ==")
        print(f"  resolved={resolve_resp.resolved} failed={resolve_resp.failed}")

        # Query pending rows again; this should be zero.
        after = excel_importer.list_pending_conflicts(session)
        print(f"  remaining pending = {after.total_pending}")

    print("\n>>> Done.")


if __name__ == "__main__":
    xlsx = Path(
        sys.argv[1]
        if len(sys.argv) > 1
        else "/sessions/relaxed-beautiful-hamilton/mnt/uploads/EcoTEA Endo WP1.xlsx"
    )
    # Second argument: optional comma-separated sheet allowlist for testing selected-sheet imports.
    selected: list[str] | None = None
    if len(sys.argv) > 2:
        selected = [s.strip() for s in sys.argv[2].split(",") if s.strip()]
        print(f"\n>>> Importing only these sheets: {selected}\n")
    main(xlsx, selected_sheets=selected)
