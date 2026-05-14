/**
 * Unit tests for the frontend API client.
 *
 * Each test stubs `globalThis.fetch` to verify both the URL/body that the
 * client constructs and the way it surfaces backend responses (or errors).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import * as api from '../api';

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------
function mockResponse(body: unknown, init: { ok?: boolean; status?: number } = {}): Response {
  const { ok = true, status = ok ? 200 : 500 } = init;
  return {
    ok,
    status,
    json: vi.fn().mockResolvedValue(body),
  } as unknown as Response;
}

let fetchSpy: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchSpy = vi.fn();
  vi.stubGlobal('fetch', fetchSpy);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// previewExcel
// ---------------------------------------------------------------------------
describe('previewExcel', () => {
  it('posts the file to /api/imports/preview and returns the parsed body', async () => {
    const body = { file_name: 'x.xlsx', sheets: [] };
    fetchSpy.mockResolvedValueOnce(mockResponse(body));

    const file = new File(['fake'], 'x.xlsx');
    const result = await api.previewExcel(file);

    expect(fetchSpy).toHaveBeenCalledOnce();
    const [url, init] = fetchSpy.mock.calls[0];
    expect(url).toBe('/api/imports/preview');
    expect(init.method).toBe('POST');
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.body as FormData).get('file')).toBe(file);
    expect(result).toEqual(body);
  });

  it('throws with the backend detail on error', async () => {
    fetchSpy.mockResolvedValueOnce(
      mockResponse({ detail: 'Only .xlsx files are supported' }, { ok: false, status: 400 }),
    );
    await expect(api.previewExcel(new File([''], 'x.txt'))).rejects.toThrow(
      'Only .xlsx files are supported',
    );
  });

  it('falls back to HTTP status when body is not JSON', async () => {
    fetchSpy.mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: vi.fn().mockRejectedValue(new Error('not json')),
    } as unknown as Response);

    await expect(api.previewExcel(new File([''], 'x.xlsx'))).rejects.toThrow('HTTP 500');
  });
});

// ---------------------------------------------------------------------------
// uploadExcel
// ---------------------------------------------------------------------------
describe('uploadExcel', () => {
  it('only attaches required field when no options are provided', async () => {
    fetchSpy.mockResolvedValueOnce(mockResponse({ import_batch_id: 1 }));

    const file = new File(['x'], 'a.xlsx');
    await api.uploadExcel(file);

    const body = fetchSpy.mock.calls[0][1].body as FormData;
    expect(body.get('file')).toBe(file);
    expect(body.has('imported_by')).toBe(false);
    expect(body.has('note')).toBe(false);
    expect(body.has('sheets')).toBe(false);
  });

  it('attaches optional fields when provided', async () => {
    fetchSpy.mockResolvedValueOnce(mockResponse({ import_batch_id: 1 }));

    await api.uploadExcel(new File(['x'], 'a.xlsx'), {
      importedBy: 'zt',
      note: 'midterm demo',
      sheets: ['Power', 'Industry'],
    });

    const body = fetchSpy.mock.calls[0][1].body as FormData;
    expect(body.get('imported_by')).toBe('zt');
    expect(body.get('note')).toBe('midterm demo');
    expect(body.get('sheets')).toBe('Power,Industry');
  });

  it('omits sheets when the list is empty', async () => {
    fetchSpy.mockResolvedValueOnce(mockResponse({ import_batch_id: 1 }));

    await api.uploadExcel(new File(['x'], 'a.xlsx'), { sheets: [] });

    const body = fetchSpy.mock.calls[0][1].body as FormData;
    expect(body.has('sheets')).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// listConflicts / resolveConflicts
// ---------------------------------------------------------------------------
describe('listConflicts', () => {
  it('calls GET /api/imports/conflicts', async () => {
    fetchSpy.mockResolvedValueOnce(mockResponse({ total_pending: 0, groups: [] }));
    const result = await api.listConflicts();
    expect(fetchSpy).toHaveBeenCalledWith('/api/imports/conflicts');
    expect(result.total_pending).toBe(0);
  });
});

describe('resolveConflicts', () => {
  it('sends a JSON body to /api/imports/conflicts/resolve', async () => {
    fetchSpy.mockResolvedValueOnce(mockResponse({ resolved: 2, failed: 0, failure_reasons: [] }));

    const resolutions = [
      { raw_row_id: 1, decision: 'TRUST_SHEET' as const },
      { raw_row_id: 2, decision: 'SKIP' as const },
    ];
    const result = await api.resolveConflicts(resolutions);

    const [url, init] = fetchSpy.mock.calls[0];
    expect(url).toBe('/api/imports/conflicts/resolve');
    expect(init.method).toBe('POST');
    expect(init.headers['Content-Type']).toBe('application/json');
    expect(JSON.parse(init.body)).toEqual(resolutions);
    expect(result.resolved).toBe(2);
  });
});

// ---------------------------------------------------------------------------
// Browse (sectors / geographies / technologies)
// ---------------------------------------------------------------------------
describe('listSectors', () => {
  it('calls GET /api/sectors and returns the JSON array', async () => {
    fetchSpy.mockResolvedValueOnce(
      mockResponse([{ sector_id: 1, sector_code: 'POWER', sector_name: 'Power' }]),
    );
    const result = await api.listSectors();
    expect(fetchSpy).toHaveBeenCalledWith('/api/sectors');
    expect(result).toHaveLength(1);
    expect(result[0].sector_code).toBe('POWER');
  });
});

describe('listGeographies', () => {
  it('calls GET /api/geographies', async () => {
    fetchSpy.mockResolvedValueOnce(
      mockResponse([{ geography_id: 1, geography_code: 'SG', geography_name: 'Singapore' }]),
    );
    const result = await api.listGeographies();
    expect(fetchSpy).toHaveBeenCalledWith('/api/geographies');
    expect(result[0].geography_code).toBe('SG');
  });
});

describe('listTechnologies', () => {
  it('omits the querystring when no filters are passed', async () => {
    fetchSpy.mockResolvedValueOnce(mockResponse({ items: [], total: 0, page: 1, page_size: 50 }));
    await api.listTechnologies();
    expect(fetchSpy).toHaveBeenCalledWith('/api/technologies');
  });

  it('builds the querystring from supplied filters', async () => {
    fetchSpy.mockResolvedValueOnce(mockResponse({ items: [], total: 0, page: 2, page_size: 25 }));
    await api.listTechnologies({
      sector_id: 1,
      geography_id: 2,
      q: 'gas',
      page: 2,
      page_size: 25,
    });
    const url = fetchSpy.mock.calls[0][0] as string;
    expect(url.startsWith('/api/technologies?')).toBe(true);
    const params = new URLSearchParams(url.split('?')[1]);
    expect(params.get('sector_id')).toBe('1');
    expect(params.get('geography_id')).toBe('2');
    expect(params.get('q')).toBe('gas');
    expect(params.get('page')).toBe('2');
    expect(params.get('page_size')).toBe('25');
  });

  it('treats sector_id=0 as a real filter, not as missing', async () => {
    fetchSpy.mockResolvedValueOnce(mockResponse({ items: [], total: 0, page: 1, page_size: 50 }));
    await api.listTechnologies({ sector_id: 0 });
    const url = fetchSpy.mock.calls[0][0] as string;
    expect(url).toContain('sector_id=0');
  });
});

describe('getTechnology', () => {
  it('hits /api/technologies/:id', async () => {
    fetchSpy.mockResolvedValueOnce(
      mockResponse({
        technology_id: 42,
        technology_code: 'TECH',
        technology_description: null,
        sector_code: 'POWER',
        sector_name: 'Power',
        geography_code: 'SG',
        technology_start_year: 2018,
        technology_lifetime_years: 30,
        grade: null,
        years: [],
      }),
    );
    const result = await api.getTechnology(42);
    expect(fetchSpy).toHaveBeenCalledWith('/api/technologies/42');
    expect(result.technology_id).toBe(42);
  });
});

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------
describe('checkHealth', () => {
  it('returns status + database fields', async () => {
    fetchSpy.mockResolvedValueOnce(mockResponse({ status: 'ok', database: 'ok' }));
    const result = await api.checkHealth();
    expect(result.status).toBe('ok');
    expect(result.database).toBe('ok');
  });

  it('throws a basic HTTP error when not ok', async () => {
    fetchSpy.mockResolvedValueOnce(mockResponse({}, { ok: false, status: 503 }));
    await expect(api.checkHealth()).rejects.toThrow('HTTP 503');
  });
});

// ---------------------------------------------------------------------------
// Convert
// ---------------------------------------------------------------------------
describe('listConvertModels', () => {
  it('calls /api/convert/models', async () => {
    fetchSpy.mockResolvedValueOnce(
      mockResponse([{ key: 'VT_SG_PWR', label: 'Power', sector: 'Power', description: '' }]),
    );
    const result = await api.listConvertModels();
    expect(fetchSpy).toHaveBeenCalledWith('/api/convert/models');
    expect(result[0].key).toBe('VT_SG_PWR');
  });
});

describe('convertVT', () => {
  it('sends model_key + vt_file + optional template', async () => {
    fetchSpy.mockResolvedValueOnce(
      mockResponse({
        download_token: 'tok',
        download_name: 'EcoTEA.xlsx',
        row_count: 100,
        sheet_name: 'Power',
        model_key: 'VT_SG_PWR',
        source_file_name: 'src.xlsx',
        template_file_name: 'tmpl.xlsx',
        bytes: 1234,
        created_at: '2026-05-13T00:00:00Z',
      }),
    );

    const src = new File(['x'], 'src.xlsx');
    const tmpl = new File(['y'], 'tmpl.xlsx');
    await api.convertVT({ modelKey: 'VT_SG_PWR', sourceFile: src, templateFile: tmpl });

    const body = fetchSpy.mock.calls[0][1].body as FormData;
    expect(body.get('model_key')).toBe('VT_SG_PWR');
    expect(body.get('vt_file')).toBe(src);
    expect(body.get('ecotea_template')).toBe(tmpl);
  });

  it('omits ecotea_template when not provided', async () => {
    fetchSpy.mockResolvedValueOnce(
      mockResponse({
        download_token: 'tok',
        download_name: 'EcoTEA.xlsx',
        row_count: 0,
        sheet_name: 'Power',
        model_key: 'VT_SG_PWR',
        source_file_name: 'src.xlsx',
        template_file_name: 'bundled',
        bytes: 0,
        created_at: '2026-05-13T00:00:00Z',
      }),
    );
    const src = new File(['x'], 'src.xlsx');
    await api.convertVT({ modelKey: 'VT_SG_PWR', sourceFile: src });
    const body = fetchSpy.mock.calls[0][1].body as FormData;
    expect(body.has('ecotea_template')).toBe(false);
  });
});

describe('conversionDownloadUrl', () => {
  it('builds the download URL and percent-encodes the token', () => {
    expect(api.conversionDownloadUrl('abc123')).toBe('/api/convert/download/abc123');
    expect(api.conversionDownloadUrl('with space/slash')).toBe(
      '/api/convert/download/with%20space%2Fslash',
    );
  });
});

describe('previewFromConversion', () => {
  it('calls the by-token endpoint as POST', async () => {
    fetchSpy.mockResolvedValueOnce(mockResponse({ file_name: 'x', sheets: [] }));
    await api.previewFromConversion('tok-1');
    const [url, init] = fetchSpy.mock.calls[0];
    expect(url).toBe('/api/imports/preview/from-conversion?token=tok-1');
    expect(init.method).toBe('POST');
  });

  it('url-encodes the token', async () => {
    fetchSpy.mockResolvedValueOnce(mockResponse({ file_name: 'x', sheets: [] }));
    await api.previewFromConversion('a/b c');
    expect(fetchSpy.mock.calls[0][0]).toBe('/api/imports/preview/from-conversion?token=a%2Fb%20c');
  });
});

describe('importFromConversion', () => {
  it('sends optional metadata via form data', async () => {
    fetchSpy.mockResolvedValueOnce(
      mockResponse({
        import_batch_id: 7,
        file_name: 'f',
        imported_at: '2026-05-13',
        rows_imported: 1,
        rows_skipped: 0,
        rows_pending: 0,
        issues: 0,
        sheets: [],
        duration_ms: 10,
      }),
    );
    await api.importFromConversion({
      token: 'tok',
      importedBy: 'zt',
      note: 'demo',
      sheets: ['Power'],
    });
    const [url, init] = fetchSpy.mock.calls[0];
    expect(url).toBe('/api/imports/from-conversion?token=tok');
    expect(init.method).toBe('POST');
    const body = init.body as FormData;
    expect(body.get('imported_by')).toBe('zt');
    expect(body.get('note')).toBe('demo');
    expect(body.get('sheets')).toBe('Power');
  });
});
