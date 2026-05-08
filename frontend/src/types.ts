/**
 * Type definitions kept in sync with backend schemas.py.
 */

export interface SheetPreview {
  sheet_name: string;
  is_known: boolean;
  sector_code: string | null;
  data_rows: number;
}

export interface FilePreview {
  file_name: string;
  sheets: SheetPreview[];
}

export interface ImportSheetSummary {
  sheet_name: string;
  rows_total: number;
  rows_imported: number;
  rows_skipped: number;
  rows_pending: number;
  issues: number;
}

export interface ImportResult {
  import_batch_id: number;
  file_name: string;
  imported_at: string; // ISO datetime
  rows_imported: number;
  rows_skipped: number;
  rows_pending: number;
  issues: number;
  sheets: ImportSheetSummary[];
  duration_ms: number;
}

export interface ConflictRow {
  raw_row_id: number;
  excel_row_number: number;
}

export interface ConflictGroup {
  group_id: string;
  sheet_name: string;
  sheet_sector_code: string | null;
  a_column_value: string | null;
  a_column_sector_code: string | null;
  rows: ConflictRow[];
  message: string;
}

export interface ConflictListResponse {
  total_pending: number;
  groups: ConflictGroup[];
}

export type ConflictDecision = 'TRUST_SHEET' | 'TRUST_A' | 'SKIP';

export interface ConflictResolution {
  raw_row_id: number;
  decision: ConflictDecision;
}

export interface ConflictResolveResponse {
  resolved: number;
  failed: number;
  failure_reasons: string[];
}

// =============================================================================
// Browse
// =============================================================================
export interface Sector {
  sector_id: number;
  sector_code: string;
  sector_name: string;
}

export interface Geography {
  geography_id: number;
  geography_code: string;
  geography_name: string | null;
}

export interface TechnologyListItem {
  technology_id: number;
  technology_code: string;
  technology_description: string | null;
  sector_code: string;
  sector_name: string;
  geography_code: string;
  technology_start_year: number | null;
  technology_lifetime_years: number | null;
  grade: string | null;
  year_count: number;
  year_min: number | null;
  year_max: number | null;
}

export interface TechnologyListResponse {
  items: TechnologyListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface CommodityRow {
  commodity_code: string;
  commodity_order: number;
  share_value: string | null; // Decimal serialized as string
  share_text: string | null;
  demand_value: string | null;
  demand_text: string | null;
}

export interface ConstraintDetail {
  detail_type: string;
  detail_value: string | null;
  detail_unit: string | null;
}

export interface TechnologyYearOut {
  technology_year_id: number;
  data_year: number;
  raw_row_id: number | null;

  emission_factor: string | null;
  emission_factor_unit: string | null;
  base_currency: string | null;
  capex: string | null;
  capex_unit: string | null;
  fixed_opex: string | null;
  fixed_opex_unit: string | null;
  variable_opex: string | null;
  variable_opex_unit: string | null;
  tax_cost: string | null;
  subsidy_cost: string | null;

  efficiency_value: string | null;
  efficiency_text: string | null;
  efficiency_unit: string | null;
  technology_efficiency: string | null;
  capacity_to_activity_factor: string | null;
  heat_rate: string | null;

  capacity_value: string | null;
  capacity_bound_type: string | null;

  constraint_details: ConstraintDetail[];
  commodities: CommodityRow[];
}

export interface TechnologyDetail {
  technology_id: number;
  technology_code: string;
  technology_description: string | null;
  sector_code: string;
  sector_name: string;
  geography_code: string;
  technology_start_year: number | null;
  technology_lifetime_years: number | null;
  grade: string | null;
  years: TechnologyYearOut[];
}

export interface ApiError {
  detail: string;
}
