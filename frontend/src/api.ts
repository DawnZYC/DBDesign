import type {
  ApiError,
  ConflictListResponse,
  ConflictResolution,
  ConflictResolveResponse,
  FilePreview,
  Geography,
  ImportResult,
  Sector,
  TechnologyDetail,
  TechnologyListResponse,
} from './types';

const API_BASE = '/api';

async function parseError(response: Response): Promise<string> {
  let message = `HTTP ${response.status}`;
  try {
    const body = (await response.json()) as ApiError;
    if (body.detail) message = body.detail;
  } catch {
    // 后端返回非 JSON
  }
  return message;
}

/**
 * 预览 Excel 的 sheet 列表（不入库）。
 */
export async function previewExcel(file: File): Promise<FilePreview> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(`${API_BASE}/imports/preview`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) throw new Error(await parseError(response));
  return (await response.json()) as FilePreview;
}

/**
 * 上传 Excel 并触发导入。
 */
export async function uploadExcel(
  file: File,
  options?: {
    importedBy?: string;
    note?: string;
    sheets?: string[];
    columnOverrides?: import('./types').ColumnOverrides;
  },
): Promise<ImportResult> {
  const formData = new FormData();
  formData.append('file', file);
  if (options?.importedBy) formData.append('imported_by', options.importedBy);
  if (options?.note) formData.append('note', options.note);
  if (options?.sheets && options.sheets.length > 0) {
    formData.append('sheets', options.sheets.join(','));
  }
  // M5: 列对齐复核确认后的「陌生列 -> 标准列」映射
  if (options?.columnOverrides && Object.keys(options.columnOverrides).length > 0) {
    formData.append('column_overrides', JSON.stringify(options.columnOverrides));
  }

  const response = await fetch(`${API_BASE}/imports`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) throw new Error(await parseError(response));
  return (await response.json()) as ImportResult;
}

/**
 * 列出所有待复核冲突（按 sheet + A 列值分组）。
 */
export async function listConflicts(): Promise<ConflictListResponse> {
  const response = await fetch(`${API_BASE}/imports/conflicts`);
  if (!response.ok) throw new Error(await parseError(response));
  return (await response.json()) as ConflictListResponse;
}

/**
 * 提交冲突复核结果。
 */
export async function resolveConflicts(
  resolutions: ConflictResolution[],
): Promise<ConflictResolveResponse> {
  const response = await fetch(`${API_BASE}/imports/conflicts/resolve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(resolutions),
  });
  if (!response.ok) throw new Error(await parseError(response));
  return (await response.json()) as ConflictResolveResponse;
}

// ---------------------------------------------------------------------------
// 浏览
// ---------------------------------------------------------------------------
export async function listSectors(): Promise<Sector[]> {
  const response = await fetch(`${API_BASE}/sectors`);
  if (!response.ok) throw new Error(await parseError(response));
  return (await response.json()) as Sector[];
}

export async function listGeographies(): Promise<Geography[]> {
  const response = await fetch(`${API_BASE}/geographies`);
  if (!response.ok) throw new Error(await parseError(response));
  return (await response.json()) as Geography[];
}

export interface TechFilters {
  sector_id?: number;
  geography_id?: number;
  q?: string;
  page?: number;
  page_size?: number;
}

export async function listTechnologies(
  filters: TechFilters = {},
): Promise<TechnologyListResponse> {
  const params = new URLSearchParams();
  if (filters.sector_id != null) params.set('sector_id', String(filters.sector_id));
  if (filters.geography_id != null)
    params.set('geography_id', String(filters.geography_id));
  if (filters.q) params.set('q', filters.q);
  if (filters.page != null) params.set('page', String(filters.page));
  if (filters.page_size != null) params.set('page_size', String(filters.page_size));

  const url = params.toString()
    ? `${API_BASE}/technologies?${params.toString()}`
    : `${API_BASE}/technologies`;

  const response = await fetch(url);
  if (!response.ok) throw new Error(await parseError(response));
  return (await response.json()) as TechnologyListResponse;
}

export async function getTechnology(technologyId: number): Promise<TechnologyDetail> {
  const response = await fetch(`${API_BASE}/technologies/${technologyId}`);
  if (!response.ok) throw new Error(await parseError(response));
  return (await response.json()) as TechnologyDetail;
}

/**
 * 健康检查。
 */
export async function checkHealth(): Promise<{ status: string; database: string }> {
  const response = await fetch(`${API_BASE}/health`);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return (await response.json()) as { status: string; database: string };
}

// ---------------------------------------------------------------------------
// Chat / AI 助手（M4）
// ---------------------------------------------------------------------------
import type { RawRowDetail } from './types';

/**
 * SSE 回调集合（由 useStreamChat 提供）。
 * 每种 SSE event 对应一个可选回调，调用方按需实现。
 */
export interface StreamCallbacks {
  onAgentStart?: (node: string) => void;
  onPlan?: (steps: string[]) => void;
  onToken?: (delta: string) => void;
  onToolCall?: (tool: string, args: Record<string, unknown>) => void;
  onToolResult?: (data: Record<string, unknown>) => void;
  onChart?: (spec: Record<string, unknown>) => void;
  onError?: (message: string) => void;
  onDone?: (traceId: string) => void;
}

export interface ChatHistoryMessage {
  role: 'user' | 'assistant';
  content: string;
}

/**
 * POST /api/chat/stream — 发起 SSE 对话流。
 *
 * 使用原生 fetch + ReadableStream 手动解析 SSE，避免引入额外依赖。
 * @microsoft/fetch-event-source 支持 POST SSE，是更完整的方案（见 M4 依赖），
 * 这里为了确保轻量可用，改用手动解析实现。
 *
 * @returns AbortController，调用方可在需要时 abort()
 */
export function streamChat(
  message: string,
  history: ChatHistoryMessage[],
  callbacks: StreamCallbacks,
): AbortController {
  const ctrl = new AbortController();

  const run = async () => {
    let response: Response;
    try {
      response = await fetch(`${API_BASE}/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, history }),
        signal: ctrl.signal,
      });
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        callbacks.onError?.(`网络错误：${(err as Error).message}`);
        callbacks.onDone?.('');
      }
      return;
    }

    if (!response.ok) {
      callbacks.onError?.(`HTTP ${response.status}`);
      callbacks.onDone?.('');
      return;
    }

    const reader = response.body?.getReader();
    if (!reader) {
      callbacks.onError?.('无法读取响应流');
      callbacks.onDone?.('');
      return;
    }

    const decoder = new TextDecoder();
    let buffer = '';

    // SSE 手动解析。
    // 兼容性要点（这里栽过坑）：
    //   - sse-starlette 2.x 在字段之间用 "\r\n"、事件之间用 "\r\n\r\n"。
    //   - 之前用 buffer.split('\n\n') —— 在 "\r\n\r\n" 里两个 '\n' 中间夹着 '\r'，
    //     永远 split 不出来，所以前端从来没拿到过任何事件。
    //   - 标准 SSE 也允许 "\n\n" 或 "\r\r"，下面用正则一次性兼容。
    //   - 一条事件内 "data:" 可能出现多次（SSE 规范允许多行 data，最终用 '\n' 拼接）。
    const EVENT_DELIM = /\r\n\r\n|\n\n|\r\r/;
    const LINE_DELIM = /\r\n|\n|\r/;

    const processChunk = (text: string) => {
      buffer += text;
      const parts = buffer.split(EVENT_DELIM);
      // 最后一段可能是被切断的、未完整的事件块，留在 buffer 里
      buffer = parts.pop() ?? '';

      for (const block of parts) {
        if (!block.trim()) continue;
        let eventType = 'message';
        const dataLines: string[] = [];
        for (const line of block.split(LINE_DELIM)) {
          if (!line) continue;
          if (line.startsWith(':')) continue;             // SSE 注释行，忽略
          if (line.startsWith('event:')) {
            eventType = line.slice(6).trimStart().trim();
          } else if (line.startsWith('data:')) {
            // SSE 规范：'data:' 后面的首个空格要剥掉
            const v = line.slice(5);
            dataLines.push(v.startsWith(' ') ? v.slice(1) : v);
          }
          // 其余字段（id:/retry:/etc.）暂不需要
        }
        if (dataLines.length === 0) continue;
        const dataLine = dataLines.join('\n');
        try {
          const data = JSON.parse(dataLine) as Record<string, unknown>;
          handleSseEvent(eventType, data);
        } catch {
          // 忽略非 JSON 行
        }
      }
    };

    const handleSseEvent = (type: string, data: Record<string, unknown>) => {
      switch (type) {
        case 'agent_start':
          callbacks.onAgentStart?.(data.node as string);
          break;
        case 'plan':
          callbacks.onPlan?.(data.steps as string[]);
          break;
        case 'token':
          callbacks.onToken?.(data.delta as string);
          break;
        case 'tool_call':
          callbacks.onToolCall?.(
            data.tool as string,
            (data.args as Record<string, unknown>) ?? {},
          );
          break;
        case 'tool_result':
          callbacks.onToolResult?.(data);
          break;
        case 'chart':
          callbacks.onChart?.(data.spec as Record<string, unknown>);
          break;
        case 'error':
          callbacks.onError?.(data.message as string);
          break;
        case 'done':
          callbacks.onDone?.(data.trace_id as string);
          break;
      }
    };

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        processChunk(decoder.decode(value, { stream: true }));
      }
      // 流结束时：把 decoder 内部还没刷出的字节也吐出来，并强制把 buffer 当作最后一个事件块解析
      const tail = decoder.decode();
      if (tail) buffer += tail;
      if (buffer.trim()) {
        // 直接把剩余 buffer 当成一个完整 block 处理（追加分隔符触发 split）
        processChunk('\r\n\r\n');
      }
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        callbacks.onError?.(`流读取错误：${(err as Error).message}`);
        callbacks.onDone?.('');
      }
    } finally {
      reader.releaseLock();
    }
  };

  void run();
  return ctrl;
}

/**
 * GET /api/raw-rows/{id} — 反查源 Excel 单元格。
 */
export async function fetchRawRow(rawRowId: number): Promise<RawRowDetail> {
  const response = await fetch(`${API_BASE}/raw-rows/${rawRowId}`);
  if (!response.ok) throw new Error(await parseError(response));
  return (await response.json()) as RawRowDetail;
}
