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
  options?: { importedBy?: string; note?: string; sheets?: string[] },
): Promise<ImportResult> {
  const formData = new FormData();
  formData.append('file', file);
  if (options?.importedBy) formData.append('imported_by', options.importedBy);
  if (options?.note) formData.append('note', options.note);
  if (options?.sheets && options.sheets.length > 0) {
    formData.append('sheets', options.sheets.join(','));
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
 * Health check.
 */
export async function checkHealth(): Promise<{ status: string; database: string }> {
  const response = await fetch(`${API_BASE}/health`);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return (await response.json()) as { status: string; database: string };
}
