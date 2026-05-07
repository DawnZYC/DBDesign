-- =============================================================================
-- EcoTEA WP1 — PostgreSQL Schema (v2)
-- 15 张表：导入审计 + 字典 + 主数据 + Anchor + Satellite + 异常追踪
-- =============================================================================
-- 执行：psql -U <user> -d <db> -f 001_init_schema.sql
-- 重复执行安全（CREATE TABLE IF NOT EXISTS）
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- 1. import_batch — 一次 Excel 文件导入
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS import_batch (
    import_batch_id BIGSERIAL PRIMARY KEY,
    file_name       TEXT        NOT NULL,
    file_hash       TEXT,
    imported_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    imported_by     TEXT,
    note            TEXT
);
CREATE INDEX IF NOT EXISTS idx_import_batch_imported_at
    ON import_batch (imported_at DESC);

-- -----------------------------------------------------------------------------
-- 2. raw_excel_row — 原始 Excel 行（用于追溯和纠错）
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw_excel_row (
    raw_row_id        BIGSERIAL PRIMARY KEY,
    import_batch_id   BIGINT  NOT NULL REFERENCES import_batch(import_batch_id) ON DELETE CASCADE,
    source_sheet_name TEXT    NOT NULL,
    excel_row_number  INTEGER NOT NULL,
    row_type          TEXT    NOT NULL DEFAULT 'data',
    raw_cells         JSONB   NOT NULL,
    normalized_status TEXT    NOT NULL DEFAULT 'pending'
);
CREATE INDEX IF NOT EXISTS idx_raw_row_batch
    ON raw_excel_row (import_batch_id);
CREATE INDEX IF NOT EXISTS idx_raw_row_sheet_row
    ON raw_excel_row (source_sheet_name, excel_row_number);

-- -----------------------------------------------------------------------------
-- 3. sector — 业务行业字典（不存 sheet name）
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sector (
    sector_id   SMALLSERIAL PRIMARY KEY,
    sector_code TEXT NOT NULL UNIQUE,
    sector_name TEXT NOT NULL
);

-- -----------------------------------------------------------------------------
-- 4. (REMOVED) data_source — 已合并到 traceability_record，留 data_source_name /
--    data_source_description 两个 TEXT 字段直接存
-- -----------------------------------------------------------------------------

-- -----------------------------------------------------------------------------
-- 6. geography — 地区字典
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS geography (
    geography_id   SMALLSERIAL PRIMARY KEY,
    geography_code TEXT NOT NULL UNIQUE,
    geography_name TEXT
);

-- -----------------------------------------------------------------------------
-- 11. commodity — 商品字典（含 VEDA Commodities 表全部字段）
--     可通过 backend/seed_commodities.py 从 VT_SG_PWR_GREF.xlsx 的 Commodities
--     sheet 灌入完整元数据
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS commodity (
    commodity_id          SMALLSERIAL PRIMARY KEY,
    commodity_code        TEXT NOT NULL UNIQUE,
    commodity_set         TEXT,    -- Csets：NRG（能源） / ENV（排放） / ...
    commodity_description TEXT,    -- CommDesc，例如 'Power Coal'
    unit                  TEXT,    -- 例如 PJ / kt
    lim_type              TEXT,    -- LimType，如 FX
    cts_lvl               TEXT,    -- CTSLvl 时间片层级，如 DAYNITE
    peak_ts               TEXT,    -- PeakTS
    ctype                 TEXT     -- Ctype，如 ELC
);
CREATE INDEX IF NOT EXISTS idx_commodity_set
    ON commodity (commodity_set);

-- -----------------------------------------------------------------------------
-- 5. traceability_record — 溯源记录（A:G 区域）
--     data_source 字典已合并：直接存 source_name / source_description
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS traceability_record (
    traceability_id          BIGSERIAL PRIMARY KEY,
    sector_id                SMALLINT NOT NULL REFERENCES sector(sector_id),
    raw_row_id               BIGINT            REFERENCES raw_excel_row(raw_row_id) ON DELETE SET NULL,
    wp_title_raw             TEXT,
    data_owner_raw           TEXT,
    data_provider_raw        TEXT,
    data_user_raw            TEXT,
    usage_purpose            TEXT,
    data_source_name         TEXT,    -- 原 data_source.source_name（D 列）
    data_source_description  TEXT,    -- 原 data_source.source_description（E 列）
    source_sheet_name        TEXT,
    source_excel_row         INTEGER
);
CREATE INDEX IF NOT EXISTS idx_trace_sector
    ON traceability_record (sector_id);
CREATE INDEX IF NOT EXISTS idx_trace_raw_row
    ON traceability_record (raw_row_id);
CREATE INDEX IF NOT EXISTS idx_trace_data_source
    ON traceability_record (data_source_name);

-- -----------------------------------------------------------------------------
-- 7. technology_process — 技术/process 主数据
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS technology_process (
    technology_id             BIGSERIAL PRIMARY KEY,
    sector_id                 SMALLINT NOT NULL REFERENCES sector(sector_id),
    geography_id              SMALLINT NOT NULL REFERENCES geography(geography_id),
    technology_code           TEXT     NOT NULL,
    technology_description    TEXT,
    technology_start_year     SMALLINT,
    technology_lifetime_years SMALLINT,
    grade                     TEXT,
    UNIQUE (technology_code, geography_id)
);
CREATE INDEX IF NOT EXISTS idx_tech_sector
    ON technology_process (sector_id);

-- -----------------------------------------------------------------------------
-- 8. technology_year — Anchor 表（某技术在某一年）
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS technology_year (
    technology_year_id BIGSERIAL PRIMARY KEY,
    technology_id      BIGINT   NOT NULL REFERENCES technology_process(technology_id) ON DELETE CASCADE,
    traceability_id    BIGINT            REFERENCES traceability_record(traceability_id),
    raw_row_id         BIGINT            REFERENCES raw_excel_row(raw_row_id) ON DELETE SET NULL,
    data_year          SMALLINT NOT NULL,
    UNIQUE (technology_id, data_year)
);
CREATE INDEX IF NOT EXISTS idx_techyear_tech
    ON technology_year (technology_id);
CREATE INDEX IF NOT EXISTS idx_techyear_year
    ON technology_year (data_year);

-- -----------------------------------------------------------------------------
-- 9. technology_year_ecotea_parameter — EcoTEA 参数（O:Y）
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS technology_year_ecotea_parameter (
    technology_year_id   BIGINT PRIMARY KEY REFERENCES technology_year(technology_year_id) ON DELETE CASCADE,
    emission_factor      NUMERIC,
    emission_factor_unit TEXT,
    base_currency        TEXT,
    capex                NUMERIC,
    capex_unit           TEXT,
    fixed_opex           NUMERIC,
    fixed_opex_unit      TEXT,
    variable_opex        NUMERIC,
    variable_opex_unit   TEXT,
    tax_cost             NUMERIC,
    subsidy_cost         NUMERIC
);

-- -----------------------------------------------------------------------------
-- 10. technology_year_wp_descriptor — WP 技术描述（Z, AA, AF, AG）
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS technology_year_wp_descriptor (
    technology_year_id          BIGINT PRIMARY KEY REFERENCES technology_year(technology_year_id) ON DELETE CASCADE,
    efficiency_value            NUMERIC,
    efficiency_text             TEXT,
    efficiency_unit             TEXT,
    technology_efficiency       NUMERIC,
    capacity_to_activity_factor NUMERIC,
    heat_rate                   NUMERIC
);

-- -----------------------------------------------------------------------------
-- 12. technology_year_commodity — 技术-年份-商品（AB:AE）
-- 多商品组合（如 PWRBMS+PWACOA）拆成多行，commodity_order 保序
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS technology_year_commodity (
    technology_year_commodity_id BIGSERIAL PRIMARY KEY,
    technology_year_id           BIGINT   NOT NULL REFERENCES technology_year(technology_year_id) ON DELETE CASCADE,
    commodity_id                 SMALLINT NOT NULL REFERENCES commodity(commodity_id),
    commodity_order              SMALLINT NOT NULL DEFAULT 1,
    commodity_share_value        NUMERIC,
    commodity_share_text         TEXT,
    commodity_demand_value       NUMERIC,
    commodity_demand_text        TEXT,
    interpolation_rule_value     NUMERIC,
    interpolation_rule_text      TEXT,
    UNIQUE (technology_year_id, commodity_order)
);
CREATE INDEX IF NOT EXISTS idx_tyc_techyear
    ON technology_year_commodity (technology_year_id);

-- -----------------------------------------------------------------------------
-- 13. technology_year_constraint — 模型约束（AH:AI）
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS technology_year_constraint (
    constraint_id      BIGSERIAL PRIMARY KEY,
    technology_year_id BIGINT NOT NULL REFERENCES technology_year(technology_year_id) ON DELETE CASCADE,
    constraint_type    TEXT   NOT NULL DEFAULT 'capacity',
    constraint_value   NUMERIC,
    bound_type         TEXT,
    constraint_unit    TEXT
);
CREATE INDEX IF NOT EXISTS idx_constraint_techyear
    ON technology_year_constraint (technology_year_id);

-- -----------------------------------------------------------------------------
-- 14. technology_year_constraint_detail — 约束详情（AJ:AL）
-- detail_type ∈ {max_import_possible, max_solar_output_allowed, capacity_special}
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS technology_year_constraint_detail (
    constraint_detail_id BIGSERIAL PRIMARY KEY,
    technology_year_id   BIGINT NOT NULL REFERENCES technology_year(technology_year_id) ON DELETE CASCADE,
    detail_type          TEXT   NOT NULL,
    detail_value         NUMERIC,
    detail_unit          TEXT
);
CREATE INDEX IF NOT EXISTS idx_constraint_detail_techyear
    ON technology_year_constraint_detail (technology_year_id);

-- -----------------------------------------------------------------------------
-- 15. data_quality_issue — 异常值/公式错误追踪
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS data_quality_issue (
    issue_id          BIGSERIAL PRIMARY KEY,
    raw_row_id        BIGINT REFERENCES raw_excel_row(raw_row_id) ON DELETE SET NULL,
    source_sheet_name TEXT,
    excel_row_number  INTEGER,
    excel_column      TEXT,
    issue_type        TEXT NOT NULL,
    original_value    TEXT,
    issue_message     TEXT
);
CREATE INDEX IF NOT EXISTS idx_issue_raw_row
    ON data_quality_issue (raw_row_id);
CREATE INDEX IF NOT EXISTS idx_issue_type
    ON data_quality_issue (issue_type);

-- -----------------------------------------------------------------------------
-- 预置 sector 字典（10 个 sheet 对应的行业）
-- -----------------------------------------------------------------------------
INSERT INTO sector (sector_code, sector_name) VALUES
    ('POWER',     'Power'),
    ('INDUSTRY',  'Industry'),
    ('PRIMARY',   'Primary'),
    ('TRANSPORT', 'Transport'),
    ('WATER',     'Water'),
    ('WASTE',     'Waste'),
    ('BUILDING',  'Building'),
    ('HOUSEHOLD', 'Household'),
    ('AGRI',      'Agri'),
    ('INFOCOMM',  'InfoComm')
ON CONFLICT (sector_code) DO NOTHING;

COMMIT;
