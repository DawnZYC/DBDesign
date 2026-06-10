/**
 * 与后端 schemas.py 保持一致的类型定义。
 */

// ---- M5: Schema-Mapping 列对齐 ----
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
  column_mapping: SheetColumnMapping | null;
}

export interface FilePreview {
  file_name: string;
  sheets: SheetPreview[];
  needs_column_review: boolean;
  standard_fields: StandardFieldInfo[];
}

/** 列对齐复核结果：{sheet: {陌生列: 标准列}}，回传给导入接口的 column_overrides。 */
export type ColumnOverrides = Record<string, Record<string, string>>;

export interface ImportSheetSummary {
  sheet_name: string;
  rows_total: number;
  rows_imported: number;
  rows_skipped: number;
  rows_pending: number;
  issues: number;
  /** M5 列对齐警告（自动对齐启用 / 低置信列被丢弃等），空数组表示快路径 */
  column_warnings: string[];
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
  /** 全文件 M5 列对齐警告汇总（带 sheet 前缀） */
  column_warnings: string[];
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
// 浏览
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

// =============================================================================
// Chat / AI 助手（M4）
// =============================================================================

/** SSE 事件中 tool_call 的数据结构 */
export interface ToolCallEvent {
  tool: string;
  args: Record<string, unknown>;
}

/** SSE 事件中 tool_result 的数据结构 */
export interface ToolResultEvent {
  tool: string;
  row_count?: number;
  truncated?: boolean;
  metric?: string;
  sql_summary?: string;
}

/** LangGraph 节点名称 */
export type AgentNode = 'planner' | 'sql_gen' | 'interpreter' | 'visualizer';

/** 单条对话消息（用户或 AI） */
export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  /** 消息文本（用户消息 / AI 流式拼接文本） */
  content: string;
  /** Planner 步骤列表（assistant only） */
  plan?: string[];
  /** 工具调用列表（assistant only） */
  toolCalls?: ToolCallEvent[];
  /** 工具返回列表（assistant only，与 toolCalls 按顺序对应） */
  toolResults?: ToolResultEvent[];
  /** ECharts option（assistant only，Visualizer 输出） */
  chartSpec?: Record<string, unknown>;
  /** 当前活跃节点（streaming 时显示） */
  currentNode?: AgentNode;
  /** 消息状态 */
  status?: 'streaming' | 'done' | 'error';
  /** 错误信息（status === 'error' 时） */
  errorMessage?: string;
}

/** GET /api/raw-rows/{id} 响应 */
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
