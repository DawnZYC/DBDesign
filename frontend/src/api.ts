import type {
  ApiError,
  ConflictListResponse,
  ConflictResolution,
  ConflictResolveResponse,
  ConvertModelInfo,
  ConvertResult,
  EmissionFactorOut,
  EmissionFactorUpsert,
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
    // Backend returned non-JSON.
  }
  return message;
}

/**
 * Preview the Excel sheet list without writing to the database.
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
 * Upload Excel and start the import.
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
  // M5: user-confirmed source-to-canonical column mapping from the review UI.
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
 * List conflicts pending review, grouped by sheet and column A value.
 */
export async function listConflicts(): Promise<ConflictListResponse> {
  const response = await fetch(`${API_BASE}/imports/conflicts`);
  if (!response.ok) throw new Error(await parseError(response));
  return (await response.json()) as ConflictListResponse;
}

/**
 * Submit conflict review results.
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
// Browse
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

export async function listTechnologies(filters: TechFilters = {}): Promise<TechnologyListResponse> {
  const params = new URLSearchParams();
  if (filters.sector_id != null) params.set('sector_id', String(filters.sector_id));
  if (filters.geography_id != null) params.set('geography_id', String(filters.geography_id));
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
 * Manually set (or clear) the emission factor for one technology-year.
 * Creates the technology-year / parameter rows if they don't exist yet.
 */
export async function upsertEmissionFactor(
  technologyId: number,
  payload: EmissionFactorUpsert,
): Promise<EmissionFactorOut> {
  const response = await fetch(`${API_BASE}/technologies/${technologyId}/emission-factors`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(await parseError(response));
  return (await response.json()) as EmissionFactorOut;
}

/**
 * Health check.
 */
export interface HealthInfo {
  status: string;
  database: string;
  llm?: { provider: string; model?: string | null; configured: boolean; ok?: boolean } | null;
}

export async function checkHealth(): Promise<HealthInfo> {
  const response = await fetch(`${API_BASE}/health`);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return (await response.json()) as HealthInfo;
}

// ---------------------------------------------------------------------------
// Convert (VT -> EcoTEA)
// ---------------------------------------------------------------------------
export async function listConvertModels(): Promise<ConvertModelInfo[]> {
  const response = await fetch(`${API_BASE}/convert/models`);
  if (!response.ok) throw new Error(await parseError(response));
  return (await response.json()) as ConvertModelInfo[];
}

export async function convertVT(args: {
  modelKey: string;
  sourceFile: File;
  templateFile?: File;
}): Promise<ConvertResult> {
  const formData = new FormData();
  formData.append('model_key', args.modelKey);
  formData.append('vt_file', args.sourceFile);
  if (args.templateFile) {
    formData.append('ecotea_template', args.templateFile);
  }
  const response = await fetch(`${API_BASE}/convert`, {
    method: 'POST',
    body: formData,
  });
  if (!response.ok) throw new Error(await parseError(response));
  return (await response.json()) as ConvertResult;
}

/** Build the absolute URL for the converted file download endpoint. */
export function conversionDownloadUrl(token: string): string {
  return `${API_BASE}/convert/download/${encodeURIComponent(token)}`;
}

export async function previewFromConversion(token: string): Promise<FilePreview> {
  const response = await fetch(
    `${API_BASE}/imports/preview/from-conversion?token=${encodeURIComponent(token)}`,
    { method: 'POST' },
  );
  if (!response.ok) throw new Error(await parseError(response));
  return (await response.json()) as FilePreview;
}

export async function importFromConversion(args: {
  token: string;
  importedBy?: string;
  note?: string;
  sheets?: string[];
  columnOverrides?: import('./types').ColumnOverrides;
}): Promise<ImportResult> {
  const formData = new FormData();
  if (args.importedBy) formData.append('imported_by', args.importedBy);
  if (args.note) formData.append('note', args.note);
  if (args.sheets && args.sheets.length > 0) {
    formData.append('sheets', args.sheets.join(','));
  }
  // M5: user-confirmed column alignment for a converted workbook with a drifted layout
  if (args.columnOverrides && Object.keys(args.columnOverrides).length > 0) {
    formData.append('column_overrides', JSON.stringify(args.columnOverrides));
  }
  const response = await fetch(
    `${API_BASE}/imports/from-conversion?token=${encodeURIComponent(args.token)}`,
    { method: 'POST', body: formData },
  );
  if (!response.ok) throw new Error(await parseError(response));
  return (await response.json()) as ImportResult;
}
// ---------------------------------------------------------------------------
// Chat / AI assistant (M4)
// ---------------------------------------------------------------------------
import type { RawRowDetail } from './types';

/**
 * SSE callback set (provided by useStreamChat).
 * One optional callback per SSE event type.
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
 * POST /api/chat/stream — start the SSE chat stream.
 *
 * Parses SSE manually with fetch + ReadableStream to avoid extra deps.
 * @microsoft/fetch-event-source supports POST SSE and is the fuller option,
 * but manual parsing keeps this light and dependency-free.
 *
 * @returns AbortController; call abort() to cancel.
 */
export function streamChat(
  message: string,
  history: ChatHistoryMessage[],
  callbacks: StreamCallbacks,
  language?: string,
): AbortController {
  const ctrl = new AbortController();

  const run = async () => {
    let response: Response;
    try {
      response = await fetch(`${API_BASE}/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, history, language: language || undefined }),
        signal: ctrl.signal,
      });
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        callbacks.onError?.(`Network error: ${(err as Error).message}`);
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
      callbacks.onError?.('Unable to read the response stream');
      callbacks.onDone?.('');
      return;
    }

    const decoder = new TextDecoder();
    let buffer = '';

    // Manual SSE parsing.
    // Compatibility notes (learned the hard way):
    //   - sse-starlette 2.x uses "\r\n" between fields and "\r\n\r\n" between events.
    //   - buffer.split('\n\n') never matched (a '\r' sits between the two '\n's),
    //     so the frontend used to receive zero events.
    //   - the SSE spec also allows "\n\n" / "\r\r"; the regex below covers all.
    //   - "data:" may repeat within one event (multi-line data joined by '\n').
    const EVENT_DELIM = /\r\n\r\n|\n\n|\r\r/;
    const LINE_DELIM = /\r\n|\n|\r/;

    const processChunk = (text: string) => {
      buffer += text;
      const parts = buffer.split(EVENT_DELIM);
      // The trailing piece may be a truncated event block; keep it buffered.
      buffer = parts.pop() ?? '';

      for (const block of parts) {
        if (!block.trim()) continue;
        let eventType = 'message';
        const dataLines: string[] = [];
        for (const line of block.split(LINE_DELIM)) {
          if (!line) continue;
          if (line.startsWith(':')) continue; // SSE comment line, ignore
          if (line.startsWith('event:')) {
            eventType = line.slice(6).trimStart().trim();
          } else if (line.startsWith('data:')) {
            // Per SSE spec, strip the single space after 'data:'.
            const v = line.slice(5);
            dataLines.push(v.startsWith(' ') ? v.slice(1) : v);
          }
          // Other fields (id:/retry:/etc.) are not needed yet.
        }
        if (dataLines.length === 0) continue;
        const dataLine = dataLines.join('\n');
        try {
          const data = JSON.parse(dataLine) as Record<string, unknown>;
          handleSseEvent(eventType, data);
        } catch {
          // Ignore non-JSON lines.
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
          callbacks.onToolCall?.(data.tool as string, (data.args as Record<string, unknown>) ?? {});
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
      // On stream end, flush the decoder and parse the remaining buffer as a final block.
      const tail = decoder.decode();
      if (tail) buffer += tail;
      if (buffer.trim()) {
        // Treat the rest of the buffer as one complete block (separator forces the split).
        processChunk('\r\n\r\n');
      }
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        callbacks.onError?.(`Stream read error: ${(err as Error).message}`);
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
 * GET /api/raw-rows/{id} — trace back to the source Excel cells.
 */
export async function fetchRawRow(rawRowId: number): Promise<RawRowDetail> {
  const response = await fetch(`${API_BASE}/raw-rows/${rawRowId}`);
  if (!response.ok) throw new Error(await parseError(response));
  return (await response.json()) as RawRowDetail;
}

// ---------------------------------------------------------------------------
// RAG knowledge documents (upload / list / delete / search)
// ---------------------------------------------------------------------------
export interface RagDocumentInfo {
  file: string;
  chunks: number;
  titles: string[];
}

export interface RagSearchHit {
  text: string;
  score: number;
  metadata: Record<string, unknown>;
}

export async function uploadRagDocument(file: File): Promise<{ file: string; chunks: number }> {
  const formData = new FormData();
  formData.append('file', file);
  const response = await fetch(`${API_BASE}/rag/documents`, { method: 'POST', body: formData });
  if (!response.ok) throw new Error(await parseError(response));
  return (await response.json()) as { file: string; chunks: number };
}

export async function listRagDocuments(): Promise<RagDocumentInfo[]> {
  const response = await fetch(`${API_BASE}/rag/documents`);
  if (!response.ok) throw new Error(await parseError(response));
  return (await response.json()) as RagDocumentInfo[];
}

export async function deleteRagDocument(fileName: string): Promise<{ deleted: number }> {
  const response = await fetch(`${API_BASE}/rag/documents/${encodeURIComponent(fileName)}`, {
    method: 'DELETE',
  });
  if (!response.ok) throw new Error(await parseError(response));
  return (await response.json()) as { deleted: number };
}

export async function ragSearch(query: string, k = 3): Promise<RagSearchHit[]> {
  const response = await fetch(`${API_BASE}/rag/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, k }),
  });
  if (!response.ok) throw new Error(await parseError(response));
  const data = (await response.json()) as { hits: RagSearchHit[] };
  return data.hits;
}
