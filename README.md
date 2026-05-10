# EcoTEA WP1 Workbench

End-to-end workbench that takes a Singapore VT model file all the way into a queryable database. The web app is organised as three sequential steps in a left sidebar:

1. **Convert** — map a VT_SG_PWR / VT_SG_PRI source workbook into a unified EcoTEA workbook.
2. **Import** — load the EcoTEA workbook into the PostgreSQL schema (15 tables, 38 columns).
3. **Browse** — search, filter and inspect imported technologies, including yearly costs, performance, capacity and output commodities.

After a successful conversion, the produced workbook is cached on the backend; clicking **Send to import** in the Convert step hands the file to the Import step without re-uploading it.

- Backend: Python 3.13 / FastAPI / SQLAlchemy 2 / openpyxl / pandas
- Frontend: React 18 / Vite / TypeScript
- Database: local PostgreSQL instance

## Project Structure

```text
DBDesign/
├── sql/
│   └── 001_init_schema.sql              # DDL for 15 tables, including constraints, indexes, and sector seed data
├── backend/                             # FastAPI service
│   ├── app/
│   │   ├── main.py                      # FastAPI entry point
│   │   ├── config.py                    # .env configuration
│   │   ├── database.py                  # SQLAlchemy engine and session
│   │   ├── models.py                    # ORM models for the 15 tables
│   │   ├── schemas.py                   # API Pydantic schemas
│   │   ├── assets/
│   │   │   └── ecotea_template.xlsx     # Bundled EcoTEA template used by Convert
│   │   ├── converters/                  # VT -> EcoTEA conversion engine
│   │   │   ├── base_model.py
│   │   │   ├── ecotea_writer.py
│   │   │   ├── engine.py
│   │   │   └── models/
│   │   │       ├── vt_sg_pwr.py
│   │   │       └── vt_sg_pri.py
│   │   ├── routers/
│   │   │   ├── health.py                # GET /api/health
│   │   │   ├── convert.py               # POST /api/convert (VT -> EcoTEA)
│   │   │   ├── imports.py               # POST /api/imports (+ /from-conversion handoff)
│   │   │   └── browse.py                # GET /api/technologies, /sectors, /geographies
│   │   └── services/
│   │       ├── value_cleaner.py         # Placeholder, formula-error, and mixed-text cleaning
│   │       └── excel_importer.py        # Main import logic
│   ├── requirements.txt
│   ├── .env.example
│   └── README.md
├── frontend/                            # React + Vite + TypeScript SPA
│   ├── src/...
│   ├── package.json
│   ├── vite.config.ts
│   └── README.md
├── EcoTEA_WP1_ER_Diagram_v2.html        # Visual design document
├── EcoTEA_Design_Review.html
├── EcoTEA_Sample_Row_Mapping.html
└── README.md
```

## End-to-End Startup

### 1. Prepare PostgreSQL

Assuming you already have local PostgreSQL running with user `postgres` on port 5432, create the database:

```bash
psql -U postgres -c "CREATE DATABASE ecotea;"
psql -U postgres -d ecotea -f sql/001_init_schema.sql
```

The final expected output is `COMMIT`. The `sector` table is seeded with 10 rows from POWER through INFOCOMM.

### 2. Start the Backend

```bash
cd backend

conda activate excelagent
pip install -r requirements.txt

cp .env.example .env               # Edit DATABASE_URL as needed.

uvicorn app.main:app --reload --port 8000
```

Without conda, you can use:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

- API docs: http://localhost:8000/docs
- Health check: http://localhost:8000/api/health, expected response `{"status":"ok","database":"ok"}`

### 3. Start the Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The sidebar offers three numbered steps:

- **01 Convert** — pick a source model (VT_SG_PWR or VT_SG_PRI), upload the VT workbook (the EcoTEA template is bundled, but you can supply a custom one), then convert. After success you can download the produced workbook or click **Send to import** to hand it directly to the next step.
- **02 Import** — drop `EcoTEA Endo WP1.xlsx` (or accept the converted workbook from step 01), select sheets, import, review the summary, and resolve conflicts if any are held.
- **03 Browse** — filter and page through the technology list by sector, geography, or search, then select a row to view all yearly parameters such as CAPEX, OPEX, efficiency, capacity, and commodities.

### Convert Flow

1. Choose the source model — converters are registered in `backend/app/converters/engine.py`.
2. Drop the VT source workbook (`.xlsx`, `.xlsm` or `.xls`).
3. Optionally supply your own EcoTEA template; otherwise the bundled `assets/ecotea_template.xlsx` is used.
4. Click **Convert workbook**. The backend caches the produced file and returns a download token.
5. Either download the file or hand it off to the importer (no re-upload required).

### Import Flow

1. Select or drag in an `.xlsx` file (or accept a Convert handoff).
2. The backend preview returns sheet names, known-sector status, and data-row counts.
3. The frontend shows a checkbox list of sheets, with all known sheets selected by default.
4. The user changes the selected sheets if needed.
5. Clicking import imports only the selected sheets.
6. The summary result is displayed.

## Data Cleaning Rules

The implementation is in `backend/app/services/value_cleaner.py`.

| Input | Handling | Writes data_quality_issue |
|---|---|---|
| `'-'` / `'NA'` / empty string / whitespace | `NULL` | No |
| `#VALUE!` / `#REF!` / `#DIV/0!` / `#N/A` and similar | Main table value becomes `NULL` | Yes, with original value, row number, and column |
| Plain numbers such as `0.497` | Stored directly | No |
| `'COP: 3.91'` / `'13.33 km/litre'` | Split into `_value`, `_text`, and `_unit` | No, limited to efficiency columns |
| `'PWRBMS+PWACOA'` / `'20%+80%'` | Split by `+` into multiple `technology_year_commodity` rows, preserving `commodity_order` | No |
| Sheet name differs from column A value, such as Agri/Building | Sector comes from the sheet name; raw column A value stays in `traceability_record.wp_title_raw` | No |

## Verify Imported Data

```sql
-- Most recent import batches.
SELECT import_batch_id, file_name, imported_at, imported_by
FROM   import_batch
ORDER  BY imported_at DESC
LIMIT  5;

-- raw_excel_row counts by sheet for the latest batch.
SELECT source_sheet_name, COUNT(*) AS rows
FROM   raw_excel_row
WHERE  import_batch_id = (SELECT MAX(import_batch_id) FROM import_batch)
GROUP  BY source_sheet_name
ORDER  BY source_sheet_name;

-- Quality issue list, such as #VALUE!.
SELECT source_sheet_name, excel_row_number, excel_column,
       issue_type, original_value, issue_message
FROM   data_quality_issue
ORDER  BY issue_id DESC
LIMIT  20;

-- Multi-commodity rows, expected to show PWRBMS / PWACOA as separate rows.
SELECT ty.data_year, tp.technology_code, c.commodity_code,
       tyc.commodity_order, tyc.commodity_share_value, tyc.commodity_share_text
FROM   technology_year_commodity tyc
JOIN   technology_year ty ON ty.technology_year_id = tyc.technology_year_id
JOIN   technology_process tp ON tp.technology_id   = ty.technology_id
JOIN   commodity c            ON c.commodity_id    = tyc.commodity_id
WHERE  tp.technology_code = 'PWRBMCSTP00'
ORDER  BY ty.data_year, tyc.commodity_order;
```

## FAQ

**psql: connection refused**: confirm PostgreSQL is running with `pg_isready -h localhost -p 5432`.

**Frontend shows `Failed to fetch`**: the backend is not running or is on another port. The health pill in the header shows the specific error.

**PostgreSQL username/password is not postgres/postgres**: update `DATABASE_URL` in `backend/.env`.

**Importing the same file multiple times**: uniqueness constraints are not violated. sector, commodity, technology_process, and technology_year use upsert behavior. Each new batch adds only one `import_batch` plus its `raw_excel_row` records.

## Design References

Open these HTML files in a browser to view the visual design references:

- `EcoTEA_WP1_ER_Diagram_v2.html`: revised ER diagram with 15 tables and 5 change markers
- `EcoTEA_Design_Review.html`: review report using real Excel data against the 15-table design
- `EcoTEA_Sample_Row_Mapping.html`: single Power row mapping from Excel to database
