# EcoTEA WP1 Import Backend

FastAPI backend for importing EcoTEA Excel files into PostgreSQL using the 15-table schema.

## Structure

```text
backend/
├── app/
│   ├── main.py                     # FastAPI entry point
│   ├── config.py                   # Configuration with .env loading
│   ├── database.py                 # SQLAlchemy engine and Session
│   ├── models.py                   # ORM models for the 15 tables
│   ├── schemas.py                  # Pydantic API models
│   ├── routers/
│   │   ├── health.py               # GET /api/health
│   │   └── imports.py              # POST /api/imports
│   └── services/
│       ├── value_cleaner.py        # Cleans placeholders, formula errors, and mixed text
│       └── excel_importer.py       # Main import flow
├── requirements.txt
└── .env.example
```

## Quick Start

```bash
cd backend

# 1) Activate the conda environment and install dependencies.
conda activate excelagent
pip install -r requirements.txt

# 2) Initialize the schema from sql/.
#    First create a local PostgreSQL database such as ecotea:
#    psql -U postgres -c "CREATE DATABASE ecotea;"
psql -U postgres -d ecotea -f ../sql/001_init_schema.sql

# 3) Configure environment variables.
cp .env.example .env
# Edit .env so DATABASE_URL matches your local PostgreSQL instance.

# 4) Start the development server.
uvicorn app.main:app --reload --port 8000
```

Without conda, you can use venv:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

After startup:

- API docs: http://localhost:8000/docs
- Health check: http://localhost:8000/api/health
- Preview sheet list without writing to the database: `POST http://localhost:8000/api/imports/preview`
- Import: `POST http://localhost:8000/api/imports` with `multipart/form-data`

## Command-Line Calls

Preview sheets:

```bash
curl -X POST http://localhost:8000/api/imports/preview \
  -F "file=@../EcoTEA Endo WP1.xlsx" | python -m json.tool
```

Import all sheets:

```bash
curl -X POST http://localhost:8000/api/imports \
  -F "file=@../EcoTEA Endo WP1.xlsx" \
  -F "imported_by=zyc" \
  -F "note=first run"
```

Import selected sheets only:

```bash
curl -X POST http://localhost:8000/api/imports \
  -F "file=@../EcoTEA Endo WP1.xlsx" \
  -F "sheets=Power,Industry"
```

## Design Notes

- Data cleaning follows three rule groups aligned with the ER diagram v2:
  - Placeholders such as `-`, `NA`, and empty values become `NULL` without trace records.
  - Formula errors such as `#VALUE!` and `#REF!` become `NULL` in the main table and create `data_quality_issue` rows with the original value.
  - Mixed semantic text such as `COP: 3.91` is split into `_value`, `_text`, and `_unit`.
- Grain: each `technology_year` row represents `(technology_id, data_year)`, and five satellite tables attach to it.
- Upsert strategy: sector, geography, commodity, data_source, and technology_process are upserted by business keys. Reimporting the same file does not violate uniqueness constraints.
- Audit: every raw Excel row is preserved in `raw_excel_row.raw_cells` as JSONB.

## Verify Written Data

```sql
-- Most recent import summary.
SELECT * FROM import_batch ORDER BY import_batch_id DESC LIMIT 1;

-- Rows written per sheet.
SELECT source_sheet_name, COUNT(*)
FROM raw_excel_row
GROUP BY source_sheet_name
ORDER BY source_sheet_name;

-- Quality issue tracing.
SELECT source_sheet_name, excel_row_number, excel_column, issue_type, original_value
FROM data_quality_issue
ORDER BY issue_id DESC
LIMIT 20;
```
