-- =============================================================================
-- v2 to v3 migration script, preserving existing data
-- Changes:
--   1. Move data_source table fields into traceability_record and drop the table.
--   2. Extend commodity with commodity_set / commodity_description / unit /
--      lim_type / cts_lvl / peak_ts / ctype, and rename old commodity_name
--      to commodity_description.
-- Usage: psql -U <user> -d ecotea -f 002_migrate_v2_to_v3.sql
-- Safe to run repeatedly with IF NOT EXISTS / IF EXISTS / DO blocks.
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- 1. Add two columns to traceability_record.
-- -----------------------------------------------------------------------------
ALTER TABLE traceability_record
    ADD COLUMN IF NOT EXISTS data_source_name        TEXT,
    ADD COLUMN IF NOT EXISTS data_source_description TEXT;

-- Backfill existing data_source records into traceability_record if data_source still exists.
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
-- 2. Drop data_source_id foreign key, column, and table.
-- -----------------------------------------------------------------------------
ALTER TABLE traceability_record DROP COLUMN IF EXISTS data_source_id;
DROP TABLE IF EXISTS data_source;

CREATE INDEX IF NOT EXISTS idx_trace_data_source
    ON traceability_record (data_source_name);

-- -----------------------------------------------------------------------------
-- 3. Extend commodity table.
-- -----------------------------------------------------------------------------
ALTER TABLE commodity
    ADD COLUMN IF NOT EXISTS commodity_set         TEXT,
    ADD COLUMN IF NOT EXISTS commodity_description TEXT,
    ADD COLUMN IF NOT EXISTS unit                  TEXT,
    ADD COLUMN IF NOT EXISTS lim_type              TEXT,
    ADD COLUMN IF NOT EXISTS cts_lvl               TEXT,
    ADD COLUMN IF NOT EXISTS peak_ts               TEXT,
    ADD COLUMN IF NOT EXISTS ctype                 TEXT;

-- Migrate old commodity_name data to commodity_description if commodity_name still exists.
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
