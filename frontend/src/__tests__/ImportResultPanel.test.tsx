import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ImportResultPanel } from '../components/ImportResultPanel';
import type { ImportResult } from '../types';

const baseResult: ImportResult = {
  import_batch_id: 42,
  file_name: 'data.xlsx',
  imported_at: '2024-01-15T10:30:00.000Z',
  rows_imported: 100,
  rows_skipped: 5,
  rows_pending: 0,
  issues: 0,
  sheets: [
    {
      sheet_name: 'ELEC',
      rows_total: 105,
      rows_imported: 100,
      rows_skipped: 5,
      rows_pending: 0,
      issues: 0,
    },
  ],
  duration_ms: 1500,
};

describe('ImportResultPanel', () => {
  it('renders the "Import complete" heading', () => {
    render(<ImportResultPanel result={baseResult} />);
    expect(screen.getByRole('heading', { name: /import complete/i })).toBeInTheDocument();
  });

  it('displays the batch ID', () => {
    render(<ImportResultPanel result={baseResult} />);
    expect(screen.getByText(/Batch #42/i)).toBeInTheDocument();
  });

  it('displays imported and skipped row counts', () => {
    render(<ImportResultPanel result={baseResult} />);
    // 100 appears in both <dd> summary and <td> in the sheet table
    expect(screen.getAllByText('100').length).toBeGreaterThanOrEqual(1);
    // 5 appears in both <dd> summary and <td> in the sheet table
    expect(screen.getAllByText('5').length).toBeGreaterThanOrEqual(1);
  });

  it('displays the duration in seconds', () => {
    render(<ImportResultPanel result={baseResult} />);
    expect(screen.getByText('1.50 s')).toBeInTheDocument();
  });

  it('does NOT show the pending banner when rows_pending is 0', () => {
    render(<ImportResultPanel result={baseResult} />);
    expect(screen.queryByText(/pending sector conflict/i)).not.toBeInTheDocument();
  });

  it('shows the pending banner with the row count when rows_pending > 0', () => {
    render(<ImportResultPanel result={{ ...baseResult, rows_pending: 7 }} />);
    expect(screen.getByText(/7 rows/i)).toBeInTheDocument();
    expect(screen.getByText(/pending sector conflict/i)).toBeInTheDocument();
  });

  it('renders a "Review now" button when rows are pending and onReviewConflicts is provided', () => {
    const onReview = vi.fn();
    render(
      <ImportResultPanel
        result={{ ...baseResult, rows_pending: 3 }}
        onReviewConflicts={onReview}
      />,
    );
    const btn = screen.getByRole('button', { name: /review now/i });
    expect(btn).toBeInTheDocument();
    fireEvent.click(btn);
    expect(onReview).toHaveBeenCalledOnce();
  });

  it('renders the sheet breakdown table with sheet name and row totals', () => {
    render(<ImportResultPanel result={baseResult} />);
    expect(screen.getByText('ELEC')).toBeInTheDocument();
    expect(screen.getByText('105')).toBeInTheDocument(); // rows_total
  });

  it('renders multiple sheet rows in the table', () => {
    const result: ImportResult = {
      ...baseResult,
      sheets: [
        { sheet_name: 'ELEC',  rows_total: 100, rows_imported: 90, rows_skipped: 5, rows_pending: 5, issues: 1 },
        { sheet_name: 'TRANS', rows_total: 50,  rows_imported: 50, rows_skipped: 0, rows_pending: 0, issues: 0 },
      ],
    };
    render(<ImportResultPanel result={result} />);
    expect(screen.getByText('ELEC')).toBeInTheDocument();
    expect(screen.getByText('TRANS')).toBeInTheDocument();
  });
});
