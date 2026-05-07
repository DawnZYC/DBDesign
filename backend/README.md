# EcoTEA WP1 Import — Backend

FastAPI 后端，负责把 EcoTEA Excel 文件导入到 PostgreSQL（15 张表 schema）。

## 目录结构

```
backend/
├── app/
│   ├── main.py                     # FastAPI 入口
│   ├── config.py                   # 配置（.env 加载）
│   ├── database.py                 # SQLAlchemy engine + Session
│   ├── models.py                   # 15 张表的 ORM 模型
│   ├── schemas.py                  # Pydantic API 模型
│   ├── routers/
│   │   ├── health.py               # GET /api/health
│   │   └── imports.py              # POST /api/imports
│   └── services/
│       ├── value_cleaner.py        # 清洗 '-' / 'NA' / #VALUE! / 混合文本
│       └── excel_importer.py       # 主导入流程
├── requirements.txt
└── .env.example
```

## 快速启动

```bash
cd backend

# 1) 激活 conda 环境并装依赖
conda activate excelagent
pip install -r requirements.txt

# 2) 初始化 schema（用 sql/ 下的 DDL）
#    先在你的本地 PG 里建一个数据库，比如 ecotea：
#    psql -U postgres -c "CREATE DATABASE ecotea;"
psql -U postgres -d ecotea -f ../sql/001_init_schema.sql

# 3) 配置环境变量
cp .env.example .env
# 编辑 .env 把 DATABASE_URL 改成你本地 PG 的实际值

# 4) 启动 dev server
uvicorn app.main:app --reload --port 8000
```

> 如果你不用 conda，也可以用 venv：`python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`

启动后：
- API 文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/api/health
- 预览（拿 sheet 列表，不入库）：`POST http://localhost:8000/api/imports/preview`
- 导入：`POST http://localhost:8000/api/imports`（multipart/form-data）

## 命令行直接调用（不走前端）

预览（看文件里有哪些 sheet）：
```bash
curl -X POST http://localhost:8000/api/imports/preview \
  -F "file=@../EcoTEA Endo WP1.xlsx" | python -m json.tool
```

导入全部 sheet：
```bash
curl -X POST http://localhost:8000/api/imports \
  -F "file=@../EcoTEA Endo WP1.xlsx" \
  -F "imported_by=zyc" \
  -F "note=first run"
```

只导入指定 sheet（白名单逗号分隔）：
```bash
curl -X POST http://localhost:8000/api/imports \
  -F "file=@../EcoTEA Endo WP1.xlsx" \
  -F "sheets=Power,Industry"
```

## 设计要点

- **数据清洗 3 类规则**（与 ER 图 v2 一致）：
  - 占位符（`-`、`NA`、空）→ 直接 `NULL`，不留痕
  - 公式错误（`#VALUE!`、`#REF!` 等）→ 主表 `NULL` + 写 `data_quality_issue` 记录原值
  - 混合语义文本（`COP: 3.91`）→ 拆出 `_value` / `_text` / `_unit`
- **粒度**：每条 `technology_year` = `(technology_id, data_year)`，5 张 satellite 都挂在它下面。
- **upsert 策略**：sector / geography / commodity / data_source / technology_process 全部按业务唯一键 upsert；同一个文件重复导入不会爆唯一约束。
- **审计**：每行原始 Excel 数据完整保留在 `raw_excel_row.raw_cells` (JSONB)。

## 验证已写入数据

```sql
-- 最近一次导入的概况
SELECT * FROM import_batch ORDER BY imported_at DESC LIMIT 5;

-- 各 sheet 写入了多少行
SELECT source_sheet_name, COUNT(*)
FROM raw_excel_row
WHERE import_batch_id = (SELECT MAX(import_batch_id) FROM import_batch)
GROUP BY source_sheet_name;

-- 异常追踪
SELECT * FROM data_quality_issue ORDER BY issue_id DESC LIMIT 20;
```
