/**
 * Type definitions mirrored from backend schemas.py.
 */

// ---- M5: schema-mapping column alignment ----
export type ColumnMappingStatus = 'auto' | 'review' | 'unmatched';

export interface ColumnSuggestion {
  excel_column: string;
  excel_header: string;
  target_field: string | null;
  target_column: string | null;
  confidence: number;
  status: ColumnMappingStatus;
  reasoning: string;
}

export interface SheetColumnMapping {
  sheet_name: string;
  layout_is_standard: boolean;
  suggestions: ColumnSuggestion[];
  auto_count: number;
  review_count: number;
  unmatched_count: number;
}

export interface StandardFieldInfo {
  field: string;
  column: string;
  label: string;
  description: string;
}

export interface SheetPreview {
  sheet_name: string;
  is_known: boolean;
  sector_code: string | null;
  data_rows: number;
  /** M5 column alignment; null/absent for canonical layout, unknown sheets, or old backends */
  column_mapping?: SheetColumnMapping | null;
}

export interface FilePreview {
  file_name: string;
  sheets: SheetPreview[];
  needs_column_review?: boolean;
  standard_fields?: StandardFieldInfo[];
}

/** Review result {sheet: {source col: canonical col}}, sent as column_overrides. */
export type ColumnOverrides = Record<string, Record<string, string>>;

export interface ImportSheetSummary {
  sheet_name: string;
  rows_total: number;
  rows_imported: number;
  rows_skipped: number;
  rows_pending: number;
  issues: number;
  /** M5 column-alignment warnings (auto-mapping used / low-confidence dropped); empty = fast path */
  column_warnings?: string[];
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
  /** Aggregated M5 warnings for the whole file (prefixed with sheet name) */
  column_warnings?: string[];
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

export interface EmissionFactorUpsert {
  data_year: number;
  emission_factor: number | null;
  emission_factor_unit: string | null;
}

export interface EmissionFactorOut {
  technology_id: number;
  technology_code: string;
  technology_year_id: number;
  data_year: number;
  emission_factor: string | null;
  emission_factor_unit: string | null;
  created: boolean;
}

export interface ApiError {
  detail: string;
}

// =============================================================================
// Chat / AI assistant (M4)
// =============================================================================

/** Payload of an SSE tool_call event */
export interface ToolCallEvent {
  tool: string;
  args: Record<string, unknown>;
}

/** Payload of an SSE tool_result event */
export interface ToolResultEvent {
  tool: string;
  row_count?: number;
  truncated?: boolean;
  metric?: string;
  sql_summary?: string;
  /** Short summary of an auxiliary tool's output (terminology / unit / emission / forecast) */
  output_summary?: string;
}

/** LangGraph node names */
export type AgentNode = 'planner' | 'sql_gen' | 'tool_agent' | 'interpreter' | 'visualizer';

/** A single chat message (user or assistant) */
export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  /** Message text (user input / streamed assistant text) */
  content: string;
  /** Planner steps (assistant only) */
  plan?: string[];
  /** Tool calls (assistant only) */
  toolCalls?: ToolCallEvent[];
  /** Tool results (assistant only, ordered to match toolCalls) */
  toolResults?: ToolResultEvent[];
  /** ECharts option (assistant only, Visualizer output) */
  chartSpec?: Record<string, unknown>;
  /** Active node (shown while streaming) */
  currentNode?: AgentNode;
  /** Message status */
  status?: 'streaming' | 'done' | 'error';
  /** Error message (when status === 'error') */
  errorMessage?: string;
}

/** Response of GET /api/raw-rows/{id} */
export interface RawRowDetail {
  raw_row_id: number;
  source_sheet_name: string;
  excel_row_number: number;
  raw_cells: Record<string, unknown>;
  import_batch: {
    import_batch_id: number;
    file_name: string;
    imported_at: string;
    note: string | null;
  };
}
// ---- Convert (VT -> EcoTEA, from main) ----
export interface ConvertModelInfo {
  key: string;
  label: string;
  sector: string;
  description: string | null;
}

export interface ConvertResult {
  download_token: string;
  download_name: string;
  row_count: number;
  sheet_name: string;
  model_key: string;
  source_file_name: string;
  template_file_name: string;
  bytes: number;
  created_at: string; // ISO datetime
}
