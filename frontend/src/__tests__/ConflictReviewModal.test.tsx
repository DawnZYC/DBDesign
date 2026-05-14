/**
 * Tests for ConflictReviewModal — the sector-conflict resolution dialog.
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

vi.mock('../api', () => ({
  listConflicts:    vi.fn(),
  resolveConflicts: vi.fn(),
}));

import { listConflicts, resolveConflicts } from '../api';
import { ConflictReviewModal } from '../components/ConflictReviewModal';
import type { ConflictListResponse, ConflictResolveResponse } from '../types';

const conflictResponse: ConflictListResponse = {
  total_pending: 3,
  groups: [
    {
      group_id:            'grp-1',
      sheet_name:          'ELEC',
      sheet_sector_code:   'ELEC',
      a_column_value:      'TRANS',
      a_column_sector_code:'TRANS',
      rows: [
        { raw_row_id: 10, excel_row_number: 5 },
        { raw_row_id: 11, excel_row_number: 6 },
        { raw_row_id: 12, excel_row_number: 7 },
      ],
      message: 'Sheet says ELEC but column A says TRANS',
    },
  ],
};

const resolveOk: ConflictResolveResponse = { resolved: 3, failed: 0, failure_reasons: [] };

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(listConflicts).mockResolvedValue(conflictResponse);
  vi.mocked(resolveConflicts).mockResolvedValue(resolveOk);
});

describe('ConflictReviewModal', () => {
  it('shows a loading message while fetching conflicts', () => {
    vi.mocked(listConflicts).mockImplementation(() => new Promise(() => {}));
    render(<ConflictReviewModal onClose={vi.fn()} onResolved={vi.fn()} />);
    expect(screen.getByText(/loading conflicts/i)).toBeInTheDocument();
  });

  it('renders the conflict group after loading', async () => {
    render(<ConflictReviewModal onClose={vi.fn()} onResolved={vi.fn()} />);
    // 'ELEC' appears in <strong>, versus-value, and versus-sector spans — use getAllByText
    await waitFor(() => expect(screen.getAllByText('ELEC').length).toBeGreaterThanOrEqual(1));
  });

  it('shows the row count for the conflict group', async () => {
    render(<ConflictReviewModal onClose={vi.fn()} onResolved={vi.fn()} />);
    await waitFor(() => screen.getAllByText('ELEC'));
    // The conflict-rows span contains exactly "3 rows"; footer says "3 rows pending" — use exact string
    expect(screen.getByText('3 rows')).toBeInTheDocument();
  });

  it('shows the summary line with group count and total pending rows', async () => {
    render(<ConflictReviewModal onClose={vi.fn()} onResolved={vi.fn()} />);
    await waitFor(() => screen.getAllByText('ELEC'));
    // Footer: "1 groups · 3 rows pending"
    expect(screen.getByText(/1 groups/i)).toBeInTheDocument();
  });

  it('defaults to TRUST_SHEET radio being checked', async () => {
    render(<ConflictReviewModal onClose={vi.fn()} onResolved={vi.fn()} />);
    await waitFor(() => screen.getAllByText('ELEC'));
    const trustSheet = screen.getByRole('radio', { name: /trust sheet/i });
    expect(trustSheet).toBeChecked();
  });

  it('can switch to TRUST_A decision', async () => {
    render(<ConflictReviewModal onClose={vi.fn()} onResolved={vi.fn()} />);
    await waitFor(() => screen.getAllByText('ELEC'));
    const trustA = screen.getByRole('radio', { name: /trust column a/i });
    fireEvent.click(trustA);
    expect(trustA).toBeChecked();
    expect(screen.getByRole('radio', { name: /trust sheet/i })).not.toBeChecked();
  });

  it('can switch to SKIP decision', async () => {
    render(<ConflictReviewModal onClose={vi.fn()} onResolved={vi.fn()} />);
    await waitFor(() => screen.getAllByText('ELEC'));
    const skip = screen.getByRole('radio', { name: /skip/i });
    fireEvent.click(skip);
    expect(skip).toBeChecked();
  });

  it('calls resolveConflicts with the correct payload on submit', async () => {
    render(<ConflictReviewModal onClose={vi.fn()} onResolved={vi.fn()} />);
    await waitFor(() => screen.getAllByText('ELEC'));
    fireEvent.click(screen.getByRole('button', { name: /apply decisions/i }));
    await waitFor(() => expect(vi.mocked(resolveConflicts)).toHaveBeenCalledOnce());
    const payload = vi.mocked(resolveConflicts).mock.calls[0][0];
    // All 3 rows should be included with TRUST_SHEET (default)
    expect(payload).toHaveLength(3);
    expect(payload.every((r) => r.decision === 'TRUST_SHEET')).toBe(true);
    expect(payload.map((r) => r.raw_row_id)).toEqual(expect.arrayContaining([10, 11, 12]));
  });

  it('calls onResolved with the API response after successful submit', async () => {
    const onResolved = vi.fn();
    render(<ConflictReviewModal onClose={vi.fn()} onResolved={onResolved} />);
    await waitFor(() => screen.getAllByText('ELEC'));
    fireEvent.click(screen.getByRole('button', { name: /apply decisions/i }));
    await waitFor(() => expect(onResolved).toHaveBeenCalledWith(resolveOk));
  });

  it('calls onClose when the close (×) button is clicked', async () => {
    const onClose = vi.fn();
    render(<ConflictReviewModal onClose={onClose} onResolved={vi.fn()} />);
    await waitFor(() => screen.getAllByText('ELEC'));
    fireEvent.click(screen.getByRole('button', { name: /close/i }));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('calls onClose when the "Later" button is clicked', async () => {
    const onClose = vi.fn();
    render(<ConflictReviewModal onClose={onClose} onResolved={vi.fn()} />);
    await waitFor(() => screen.getAllByText('ELEC'));
    fireEvent.click(screen.getByRole('button', { name: /later/i }));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('shows an error when listConflicts fails', async () => {
    vi.mocked(listConflicts).mockRejectedValueOnce(new Error('Server unavailable'));
    render(<ConflictReviewModal onClose={vi.fn()} onResolved={vi.fn()} />);
    await waitFor(() =>
      expect(screen.getByText(/failed to load/i)).toBeInTheDocument(),
    );
    expect(screen.getByText('Server unavailable')).toBeInTheDocument();
  });

  it('shows "No conflicts pending" when the API returns an empty group list', async () => {
    vi.mocked(listConflicts).mockResolvedValueOnce({ total_pending: 0, groups: [] });
    render(<ConflictReviewModal onClose={vi.fn()} onResolved={vi.fn()} />);
    await waitFor(() =>
      expect(screen.getByText(/no conflicts pending/i)).toBeInTheDocument(),
    );
  });

  it('calls resolveConflicts with SKIP for a group where the SKIP radio was chosen', async () => {
    render(<ConflictReviewModal onClose={vi.fn()} onResolved={vi.fn()} />);
    await waitFor(() => screen.getAllByText('ELEC'));
    fireEvent.click(screen.getByRole('radio', { name: /skip/i }));
    fireEvent.click(screen.getByRole('button', { name: /apply decisions/i }));
    await waitFor(() => expect(vi.mocked(resolveConflicts)).toHaveBeenCalled());
    const payload = vi.mocked(resolveConflicts).mock.calls[0][0];
    expect(payload.every((r) => r.decision === 'SKIP')).toBe(true);
  });
});
