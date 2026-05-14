/**
 * Tests for ImportView — the Excel import pipeline step.
 *
 * Covers: idle → previewing → picking → importing → success/error,
 * the handoff path from ConvertView, and the ConflictReviewModal integration.
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

vi.mock('../api', () => ({
  previewExcel: vi.fn(),
  uploadExcel: vi.fn(),
  listConflicts: vi.fn(),
  resolveConflicts: vi.fn(),
  previewFromConversion: vi.fn(),
  importFromConversion: vi.fn(),
}));

import {
  previewExcel,
  uploadExcel,
  listConflicts,
  resolveConflicts,
  previewFromConversion,
  importFromConversion,
} from '../api';
import { ImportView } from '../components/ImportView';
import type { ConvertResult, FilePreview, ImportResult } from '../types';

const mockPreview: FilePreview = {
  file_name: 'test.xlsx',
  sheets: [
    { sheet_name: 'ELEC', is_known: true, sector_code: 'ELEC', data_rows: 100 },
    { sheet_name: 'TRANS', is_known: true, sector_code: 'TRANS', data_rows: 50 },
    { sheet_name: 'NOTES', is_known: false, sector_code: null, data_rows: 0 },
  ],
};

const mockImportResult: ImportResult = {
  import_batch_id: 7,
  file_name: 'test.xlsx',
  imported_at: '2024-01-15T10:30:00.000Z',
  rows_imported: 150,
  rows_skipped: 0,
  rows_pending: 0,
  issues: 0,
  sheets: [
    {
      sheet_name: 'ELEC',
      rows_total: 100,
      rows_imported: 100,
      rows_skipped: 0,
      rows_pending: 0,
      issues: 0,
    },
    {
      sheet_name: 'TRANS',
      rows_total: 50,
      rows_imported: 50,
      rows_skipped: 0,
      rows_pending: 0,
      issues: 0,
    },
  ],
  duration_ms: 800,
};

const mockHandoff: ConvertResult = {
  download_token: 'tok-xyz',
  download_name: 'converted.xlsx',
  row_count: 80,
  sheet_name: 'ELEC',
  model_key: 'VT_ELEC',
  source_file_name: 'vt_source.xlsx',
  template_file_name: 'template.xlsx',
  bytes: 10240,
  created_at: '2024-01-15T09:00:00Z',
};

function pickFile(name = 'test.xlsx') {
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  fireEvent.change(input, { target: { files: [new File(['x'], name)] } });
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(previewExcel).mockResolvedValue(mockPreview);
  vi.mocked(uploadExcel).mockResolvedValue(mockImportResult);
  vi.mocked(listConflicts).mockResolvedValue({ total_pending: 0, groups: [] });
  vi.mocked(resolveConflicts).mockResolvedValue({ resolved: 0, failed: 0, failure_reasons: [] });
  vi.mocked(previewFromConversion).mockResolvedValue(mockPreview);
  vi.mocked(importFromConversion).mockResolvedValue(mockImportResult);
});

describe('ImportView — idle state', () => {
  it('renders the file upload zone in the initial idle state', () => {
    render(<ImportView />);
    expect(
      screen.getByRole('button', { name: /select or drop an excel file/i }),
    ).toBeInTheDocument();
  });

  it('shows the optional metadata fields (imported-by and note)', () => {
    render(<ImportView />);
    expect(screen.getByPlaceholderText(/your name/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/brief description/i)).toBeInTheDocument();
  });
});

describe('ImportView — preview flow', () => {
  it('shows a spinner while the preview is loading', async () => {
    vi.mocked(previewExcel).mockImplementation(() => new Promise(() => {}));
    render(<ImportView />);
    pickFile();
    await waitFor(() => expect(screen.getByText(/reading the sheet list/i)).toBeInTheDocument());
  });

  it('transitions to the sheet-picking stage after a successful preview', async () => {
    render(<ImportView />);
    pickFile();
    // 'ELEC' appears multiple times; 'NOTES' is unique (unrecognized sheet)
    await waitFor(() => expect(screen.getAllByText('ELEC').length).toBeGreaterThanOrEqual(1));
    expect(screen.getAllByText('TRANS').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('NOTES')).toBeInTheDocument();
  });

  it('shows an error panel when the preview fails', async () => {
    vi.mocked(previewExcel).mockRejectedValueOnce(new Error('Parse error'));
    render(<ImportView />);
    pickFile();
    await waitFor(() => expect(screen.getByText(/preview failed/i)).toBeInTheDocument());
    expect(screen.getByText('Parse error')).toBeInTheDocument();
  });

  it('can reset to idle after a preview error', async () => {
    vi.mocked(previewExcel).mockRejectedValueOnce(new Error('Bad file'));
    render(<ImportView />);
    pickFile();
    await waitFor(() => screen.getByText(/preview failed/i));
    fireEvent.click(screen.getByRole('button', { name: /try again/i }));
    expect(
      screen.getByRole('button', { name: /select or drop an excel file/i }),
    ).toBeInTheDocument();
  });
});

describe('ImportView — sheet picking and import', () => {
  async function reachPickingStage() {
    render(<ImportView />);
    pickFile();
    // 'ELEC' appears multiple times (sheet_name + sector_code in SheetPicker)
    await waitFor(() => screen.getAllByText('ELEC'));
  }

  it('pre-selects known sheets and shows the import button', async () => {
    await reachPickingStage();
    // Both ELEC and TRANS are known → both pre-selected → button says "Import 2 selected sheets"
    expect(screen.getByRole('button', { name: /import 2 selected sheet/i })).toBeInTheDocument();
  });

  it('disables the import button when no sheets are selected', async () => {
    await reachPickingStage();
    const checkboxes = screen.getAllByRole('checkbox');
    // Deselect all known sheets ([0]=select-all, [1]=ELEC, [2]=TRANS)
    fireEvent.click(checkboxes[1]); // deselect ELEC
    fireEvent.click(checkboxes[2]); // deselect TRANS
    // The button should reflect 0 selected and be disabled
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /import 0 selected sheet/i })).toBeDisabled(),
    );
  });

  it('shows an importing spinner during the upload', async () => {
    vi.mocked(uploadExcel).mockImplementation(() => new Promise(() => {}));
    await reachPickingStage();
    fireEvent.click(screen.getByRole('button', { name: /import 2 selected sheet/i }));
    await waitFor(() => expect(screen.getByText(/importing/i)).toBeInTheDocument());
  });

  it('shows the ImportResultPanel after a successful import', async () => {
    await reachPickingStage();
    fireEvent.click(screen.getByRole('button', { name: /import 2 selected sheet/i }));
    await waitFor(() => expect(screen.getByText(/import complete/i)).toBeInTheDocument());
    expect(screen.getByText(/Batch #7/i)).toBeInTheDocument();
  });

  it('shows an error panel when the import fails', async () => {
    vi.mocked(uploadExcel).mockRejectedValueOnce(new Error('DB error'));
    await reachPickingStage();
    fireEvent.click(screen.getByRole('button', { name: /import 2 selected sheet/i }));
    await waitFor(() => expect(screen.getByText(/import failed/i)).toBeInTheDocument());
    expect(screen.getByText('DB error')).toBeInTheDocument();
  });

  it('can reset to idle after a successful import', async () => {
    await reachPickingStage();
    fireEvent.click(screen.getByRole('button', { name: /import 2 selected sheet/i }));
    await waitFor(() => screen.getByText(/import complete/i));
    fireEvent.click(screen.getByRole('button', { name: /import another file/i }));
    expect(
      screen.getByRole('button', { name: /select or drop an excel file/i }),
    ).toBeInTheDocument();
  });
});

describe('ImportView — handoff from Convert step', () => {
  it('shows the handoff banner and skips the file-upload step', async () => {
    render(<ImportView handoff={mockHandoff} onHandoffConsumed={vi.fn()} />);
    await waitFor(() => expect(screen.getByText(/loaded from convert step/i)).toBeInTheDocument());
    // Banner renders "File: converted.xlsx" in a span — match with regex
    expect(screen.getByText(/converted\.xlsx/i)).toBeInTheDocument();
  });

  it('calls previewFromConversion (not previewExcel) for a token handoff', async () => {
    render(<ImportView handoff={mockHandoff} onHandoffConsumed={vi.fn()} />);
    await waitFor(() => screen.getAllByText('ELEC'));
    expect(vi.mocked(previewFromConversion)).toHaveBeenCalledWith('tok-xyz');
    expect(vi.mocked(previewExcel)).not.toHaveBeenCalled();
  });

  it('calls onHandoffConsumed exactly once after processing the handoff', async () => {
    const consumed = vi.fn();
    render(<ImportView handoff={mockHandoff} onHandoffConsumed={consumed} />);
    await waitFor(() => screen.getAllByText('ELEC'));
    expect(consumed).toHaveBeenCalledOnce();
  });
});

describe('ImportView — conflict review', () => {
  it('shows the "Review now" button when import has pending rows', async () => {
    vi.mocked(uploadExcel).mockResolvedValueOnce({ ...mockImportResult, rows_pending: 5 });
    render(<ImportView />);
    pickFile();
    await waitFor(() => screen.getAllByText('ELEC'));
    fireEvent.click(screen.getByRole('button', { name: /import 2 selected sheet/i }));
    await waitFor(() => screen.getByText(/import complete/i));
    expect(screen.getByRole('button', { name: /review now/i })).toBeInTheDocument();
  });
});
