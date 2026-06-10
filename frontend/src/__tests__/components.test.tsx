/**
 * Render tests for smaller UI components.
 *
 * These tests verify that each component mounts without error and exposes the
 * key interactive elements users rely on.  The real backend is never contacted.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { FileUpload } from '../components/FileUpload';
import { SheetPicker } from '../components/SheetPicker';
import { ImportResultPanel } from '../components/ImportResultPanel';
import type { ImportResult, ImportSheetSummary, SheetPreview } from '../types';

// ---------------------------------------------------------------------------
// FileUpload
// ---------------------------------------------------------------------------
describe('FileUpload', () => {
  it('renders the drop-zone with accessible label', () => {
    render(<FileUpload onFileSelected={vi.fn()} />);
    expect(
      screen.getByRole('button', { name: /select or drop an excel file/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/click to choose a file/i)).toBeInTheDocument();
    expect(screen.getByText(/\.xlsx or \.xlsm/i)).toBeInTheDocument();
  });

  it('applies disabled class when disabled prop is true', () => {
    const { container } = render(<FileUpload onFileSelected={vi.fn()} disabled />);
    const zone = container.querySelector('.drop-zone');
    expect(zone).toHaveClass('disabled');
  });

  it('calls onFileSelected with the chosen xlsx file', () => {
    const handler = vi.fn();
    render(<FileUpload onFileSelected={handler} />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(['content'], 'data.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });
    fireEvent.change(input, { target: { files: [file] } });
    expect(handler).toHaveBeenCalledWith(file);
  });

  it('does not call onFileSelected for non-excel files and shows alert', () => {
    const handler = vi.fn();
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});
    render(<FileUpload onFileSelected={handler} />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(['content'], 'data.csv', { type: 'text/csv' });
    fireEvent.change(input, { target: { files: [file] } });
    expect(handler).not.toHaveBeenCalled();
    expect(alertSpy).toHaveBeenCalled();
    alertSpy.mockRestore();
  });

  it('does not call onFileSelected when no file is provided', () => {
    const handler = vi.fn();
    render(<FileUpload onFileSelected={handler} />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [] } });
    expect(handler).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// SheetPicker
// ---------------------------------------------------------------------------
function makeSheets(overrides: Partial<SheetPreview>[] = [{}]): SheetPreview[] {
  return overrides.map((o, i) => ({
    sheet_name: `Sheet${i + 1}`,
    is_known: true,
    sector_code: 'POWER',
    data_rows: 10 + i,
    ...o,
  }));
}

describe('SheetPicker', () => {
  it('renders file name and recognized count', () => {
    const sheets = makeSheets([{}, { is_known: false, sector_code: null }]);
    render(
      <SheetPicker
        fileName="workbook.xlsx"
        sheets={sheets}
        selected={new Set()}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText('workbook.xlsx')).toBeInTheDocument();
    expect(screen.getByText(/1 recognized of 2 sheets/i)).toBeInTheDocument();
  });

  it('marks unrecognized sheets with Unrecognized label', () => {
    const sheets = makeSheets([{ is_known: false, sector_code: null }]);
    render(
      <SheetPicker fileName="wb.xlsx" sheets={sheets} selected={new Set()} onChange={vi.fn()} />,
    );
    expect(screen.getByText('Unrecognized')).toBeInTheDocument();
  });

  it('shows sector code badge for known sheets', () => {
    const sheets = makeSheets([{ sector_code: 'POWER' }]);
    render(
      <SheetPicker fileName="wb.xlsx" sheets={sheets} selected={new Set()} onChange={vi.fn()} />,
    );
    expect(screen.getByText('POWER')).toBeInTheDocument();
  });

  it('calls onChange when a sheet checkbox is toggled on', () => {
    const onChange = vi.fn();
    const sheets = makeSheets([{}]);
    render(
      <SheetPicker fileName="wb.xlsx" sheets={sheets} selected={new Set()} onChange={onChange} />,
    );
    // The visible label contains the sheet name; find its checkbox.
    const checkbox = screen
      .getAllByRole('checkbox')
      .find((el) => !(el as HTMLInputElement).name?.includes('all')) as HTMLInputElement;
    fireEvent.click(checkbox);
    expect(onChange).toHaveBeenCalledWith(new Set(['Sheet1']));
  });

  it('calls onChange when a selected sheet checkbox is toggled off', () => {
    const onChange = vi.fn();
    const sheets = makeSheets([{}]);
    render(
      <SheetPicker
        fileName="wb.xlsx"
        sheets={sheets}
        selected={new Set(['Sheet1'])}
        onChange={onChange}
      />,
    );
    const checkboxes = screen.getAllByRole('checkbox');
    // Sheet checkbox is the second one (first is Select-all)
    fireEvent.click(checkboxes[1]);
    expect(onChange).toHaveBeenCalledWith(new Set());
  });

  it('selects all known sheets via the Select-all checkbox', () => {
    const onChange = vi.fn();
    const sheets = makeSheets([{}, {}]);
    render(
      <SheetPicker fileName="wb.xlsx" sheets={sheets} selected={new Set()} onChange={onChange} />,
    );
    const selectAll = screen.getByRole('checkbox', { name: /select all recognized/i });
    fireEvent.click(selectAll);
    expect(onChange).toHaveBeenCalledWith(new Set(['Sheet1', 'Sheet2']));
  });

  it('deselects all when all recognized sheets are already selected', () => {
    const onChange = vi.fn();
    const sheets = makeSheets([{}, {}]);
    render(
      <SheetPicker
        fileName="wb.xlsx"
        sheets={sheets}
        selected={new Set(['Sheet1', 'Sheet2'])}
        onChange={onChange}
      />,
    );
    const selectAll = screen.getByRole('checkbox', { name: /select all recognized/i });
    fireEvent.click(selectAll);
    expect(onChange).toHaveBeenCalledWith(new Set());
  });

  it('disables all checkboxes when disabled prop is true', () => {
    const sheets = makeSheets([{}]);
    render(
      <SheetPicker
        fileName="wb.xlsx"
        sheets={sheets}
        selected={new Set()}
        onChange={vi.fn()}
        disabled
      />,
    );
    screen.getAllByRole('checkbox').forEach((cb) => expect(cb).toBeDisabled());
  });
});

// ---------------------------------------------------------------------------
// ImportResultPanel
// ---------------------------------------------------------------------------
function makeSheetSummary(name: string): ImportSheetSummary {
  return {
    sheet_name: name,
    rows_total: 20,
    rows_imported: 18,
    rows_skipped: 1,
    rows_pending: 1,
    issues: 0,
  };
}

function makeImportResult(overrides: Partial<ImportResult> = {}): ImportResult {
  return {
    import_batch_id: 1,
    file_name: 'test.xlsx',
    imported_at: '2026-05-14T10:00:00Z',
    rows_imported: 42,
    rows_skipped: 3,
    rows_pending: 0,
    issues: 0,
    sheets: [makeSheetSummary('Power')],
    duration_ms: 1234,
    ...overrides,
  };
}

describe('ImportResultPanel', () => {
  it('renders "Import complete" heading and batch id', () => {
    render(<ImportResultPanel result={makeImportResult()} />);
    expect(screen.getByText(/import complete/i)).toBeInTheDocument();
    expect(screen.getByText(/batch #1/i)).toBeInTheDocument();
  });

  it('displays rows_imported count', () => {
    render(<ImportResultPanel result={makeImportResult({ rows_imported: 42 })} />);
    expect(screen.getByText('42')).toBeInTheDocument();
  });

  it('displays rows_skipped count', () => {
    render(<ImportResultPanel result={makeImportResult({ rows_skipped: 5 })} />);
    expect(screen.getByText('5')).toBeInTheDocument();
  });

  it('shows a pending-conflict banner when rows_pending > 0', () => {
    render(<ImportResultPanel result={makeImportResult({ rows_pending: 7 })} />);
    expect(screen.getByText(/7 rows/i)).toBeInTheDocument();
    expect(screen.getByText(/pending sector conflict review/i)).toBeInTheDocument();
  });

  it('does not render the pending banner when rows_pending is 0', () => {
    render(<ImportResultPanel result={makeImportResult({ rows_pending: 0 })} />);
    expect(screen.queryByText(/pending sector conflict review/i)).not.toBeInTheDocument();
  });

  it('calls onReviewConflicts when Review now button is clicked', () => {
    const onReview = vi.fn();
    render(
      <ImportResultPanel
        result={makeImportResult({ rows_pending: 3 })}
        onReviewConflicts={onReview}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /review now/i }));
    expect(onReview).toHaveBeenCalled();
  });

  it('renders a row in the sheet summary table for each sheet', () => {
    const result = makeImportResult({
      sheets: [makeSheetSummary('Power'), makeSheetSummary('Industry')],
    });
    render(<ImportResultPanel result={result} />);
    expect(screen.getByText('Power')).toBeInTheDocument();
    expect(screen.getByText('Industry')).toBeInTheDocument();
  });

  it('displays the file name and duration', () => {
    render(
      <ImportResultPanel
        result={makeImportResult({ file_name: 'my_data.xlsx', duration_ms: 2500 })}
      />,
    );
    expect(screen.getByText('my_data.xlsx')).toBeInTheDocument();
    expect(screen.getByText('2.50 s')).toBeInTheDocument();
  });
});
