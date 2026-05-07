# EcoTEA WP1 — Excel → PostgreSQL 导入工具

把 EcoTEA 的多 sheet Excel 文件（10 个行业 × 38 列）按规范化的 15 张表 schema 导入本地 PostgreSQL。

- **后端**：Python 3.11+ / FastAPI / SQLAlchemy 2 / openpyxl
- **前端**：React 18 / Vite / TypeScript
- **数据库**：PostgreSQL（本地实例）

## 项目结构

```
DBDesign/
├── sql/
│   └── 001_init_schema.sql              # 15 张表的 DDL（含约束/索引/sector 预置数据）
├── backend/                             # FastAPI 服务
│   ├── app/
│   │   ├── main.py                      # FastAPI 入口
│   │   ├── config.py                    # .env 配置
│   │   ├── database.py                  # SQLAlchemy engine + session
│   │   ├── models.py                    # 15 张表 ORM
│   │   ├── schemas.py                   # API Pydantic schema
│   │   ├── routers/
│   │   │   ├── health.py                # GET /api/health
│   │   │   └── imports.py               # POST /api/imports
│   │   └── services/
│   │       ├── value_cleaner.py         # 占位符 / 公式错误 / 混合文本清洗
│   │       └── excel_importer.py        # 主导入逻辑
│   ├── requirements.txt
│   ├── .env.example
│   └── README.md
├── frontend/                            # React + Vite + TS 单页
│   ├── src/...
│   ├── package.json
│   ├── vite.config.ts
│   └── README.md
├── EcoTEA_WP1_ER_Diagram_v2.html        # 设计文档（可视化）
├── EcoTEA_Design_Review.html
├── EcoTEA_Sample_Row_Mapping.html
└── README.md（本文件）
```

## 端到端启动

### 1. 准备 PostgreSQL

假设你本地已经有 PG（用户 `postgres`，端口 5432）。新建一个数据库：

```bash
psql -U postgres -c "CREATE DATABASE ecotea;"
psql -U postgres -d ecotea -f sql/001_init_schema.sql
```

预期输出最后一行：`COMMIT`。`sector` 表会自动预置 10 行（POWER…INFOCOMM）。

### 2. 启动后端

```bash
cd backend

conda activate excelagent          # 你的 conda 环境
pip install -r requirements.txt

cp .env.example .env               # 按需修改 DATABASE_URL

uvicorn app.main:app --reload --port 8000
```

> 不用 conda 也可：`python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`

- API 文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/api/health → 应返回 `{"status":"ok","database":"ok"}`

### 3. 启动前端

```bash
cd frontend
npm install
npm run dev
```

打开 http://localhost:5173 ，顶部有两个标签：

- **导入数据**：拖入 `EcoTEA Endo WP1.xlsx` → 选 sheet → 导入 → 看摘要 → 有冲突就「去复核」逐项确认。
- **浏览数据**：技术列表（行业/地区/搜索筛选 + 分页）→ 点某条 → 右侧出现该技术全年份的所有参数（CAPEX、OPEX、效率、容量、commodity 等）。

### 导入流程（用户视角）

1. 选/拖入 .xlsx 文件
2. 后端预览：返回 sheet 列表（包含 sheet 名 / 是否已知行业 / 数据行数）
3. 前端展示带 checkbox 的 sheet 列表，默认全部勾上已知 sheet
4. 用户取消 / 勾选要导入的 sheet
5. 点击导入 → 仅导入勾选的 sheet
6. 看汇总结果

## 数据清洗规则

代码集中在 `backend/app/services/value_cleaner.py`：

| 输入 | 处理 | 是否写 data_quality_issue |
|---|---|---|
| `'-'` / `'NA'` / 空字符串 / 空白 | → `NULL` | 否 |
| `#VALUE!` / `#REF!` / `#DIV/0!` / `#N/A` 等 | 主表 → `NULL` | **是**（含原值 + 行号 + 列号） |
| `0.497` 这类纯数字 | 直接存 | 否 |
| `'COP: 3.91'` / `'13.33 km/litre'` | 拆为 `_value` + `_text` + `_unit` | 否（仅限 efficiency 列） |
| `'PWRBMS+PWACOA'` / `'20%+80%'` | 按 `+` 拆成多条 `technology_year_commodity`（保 `commodity_order`） | 否 |
| sheet 名 ≠ A 列值（Agri/Building 异常） | sector 取 sheet 名；A 列原值留在 `traceability_record.wp_title_raw` | 否 |

## 验证已导入

```sql
-- 最近一次批次概况
SELECT import_batch_id, file_name, imported_at, imported_by
FROM   import_batch
ORDER  BY imported_at DESC
LIMIT  5;

-- 各 sheet 写了多少条 raw_excel_row
SELECT source_sheet_name, COUNT(*) AS rows
FROM   raw_excel_row
WHERE  import_batch_id = (SELECT MAX(import_batch_id) FROM import_batch)
GROUP  BY source_sheet_name
ORDER  BY source_sheet_name;

-- 异常列表（#VALUE! 等）
SELECT source_sheet_name, excel_row_number, excel_column,
       issue_type, original_value, issue_message
FROM   data_quality_issue
ORDER  BY issue_id DESC
LIMIT  20;

-- 多商品行（应能看到 PWRBMS / PWACOA 各占一行）
SELECT ty.data_year, tp.technology_code, c.commodity_code,
       tyc.commodity_order, tyc.commodity_share_value, tyc.commodity_share_text
FROM   technology_year_commodity tyc
JOIN   technology_year ty ON ty.technology_year_id = tyc.technology_year_id
JOIN   technology_process tp ON tp.technology_id   = ty.technology_id
JOIN   commodity c            ON c.commodity_id    = tyc.commodity_id
WHERE  tp.technology_code = 'PWRBMCSTP00'
ORDER  BY ty.data_year, tyc.commodity_order;
```

## 常见问题

**psql: 连接被拒** → 确认 PG 服务在跑：`pg_isready -h localhost -p 5432`。
**前端报 `Failed to fetch`** → 后端没起 / 起在别的端口；右上角 health pill 会显示具体错误。
**PostgreSQL 用户名密码不是 postgres/postgres** → 改 `backend/.env` 的 `DATABASE_URL`。
**重复导入同一文件** → 不会爆唯一约束；sector / commodity / technology_process / technology_year 全部走 upsert，新批次只多出一份 `import_batch` + `raw_excel_row`。

## 设计参考

打开下面三份 HTML 在浏览器看可视化设计：

- `EcoTEA_WP1_ER_Diagram_v2.html` — 修正版 ER 图（15 张表 + 5 处变更标记）
- `EcoTEA_Design_Review.html` — 用实际 Excel 数据对您 15 张表设计的核查报告
- `EcoTEA_Sample_Row_Mapping.html` — 单行 Power 数据从 Excel → 数据库的填表演示
