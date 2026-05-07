-- =============================================================================
-- v2 → v3 迁移脚本（保留已有数据）
-- 变更：
--   1. 把 data_source 表的字段下沉到 traceability_record（删表）
--   2. commodity 表扩列：commodity_set / commodity_description / unit /
--      lim_type / cts_lvl / peak_ts / ctype；并把旧的 commodity_name 重命名
--      为 commodity_description
-- 用法：psql -U <user> -d ecotea -f 002_migrate_v2_to_v3.sql
-- 重复执行安全（用 IF NOT EXISTS / IF EXISTS / DO blocks）
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- 1. traceability_record 增加两列
-- -----------------------------------------------------------------------------
ALTER TABLE traceability_record
    ADD COLUMN IF NOT EXISTS data_source_name        TEXT,
    ADD COLUMN IF NOT EXISTS data_source_description TEXT;

-- 把 data_source 现有记录回填到 traceability_record（仅当还存在 data_source 表时）
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE  table_schema = 'public' AND table_name = 'data_source'
    ) THEN
        UPDATE traceability_record AS t
        SET    data_source_name        = d.source_name,
               data_source_description = d.source_description
        FROM   data_source AS d
        WHERE  t.data_source_id = d.data_source_id
          AND  t.data_source_name IS NULL;
    END IF;
END $$;

-- -----------------------------------------------------------------------------
-- 2. 删 data_source_id 外键 + 列 + 表
-- -----------------------------------------------------------------------------
ALTER TABLE traceability_record DROP COLUMN IF EXISTS data_source_id;
DROP TABLE IF EXISTS data_source;

CREATE INDEX IF NOT EXISTS idx_trace_data_source
    ON traceability_record (data_source_name);

-- -----------------------------------------------------------------------------
-- 3. commodity 表扩列
-- -----------------------------------------------------------------------------
ALTER TABLE commodity
    ADD COLUMN IF NOT EXISTS commodity_set         TEXT,
    ADD COLUMN IF NOT EXISTS commodity_description TEXT,
    ADD COLUMN IF NOT EXISTS unit                  TEXT,
    ADD COLUMN IF NOT EXISTS lim_type              TEXT,
    ADD COLUMN IF NOT EXISTS cts_lvl               TEXT,
    ADD COLUMN IF NOT EXISTS peak_ts               TEXT,
    ADD COLUMN IF NOT EXISTS ctype                 TEXT;

-- 把旧的 commodity_name 数据迁移到 commodity_description（若 commodity_name 还在）
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE  table_schema = 'public' AND table_name = 'commodity'
          AND  column_name = 'commodity_name'
    ) THEN
        UPDATE commodity
        SET    commodity_description = COALESCE(commodity_description, commodity_name)
        WHERE  commodity_name IS NOT NULL;

        ALTER TABLE commodity DROP COLUMN commodity_name;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_commodity_set
    ON commodity (commodity_set);

COMMIT;
