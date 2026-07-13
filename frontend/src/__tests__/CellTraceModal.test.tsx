/**
 * CellTraceModal — source-cell trace overlay tests.
 *
 * fetchRawRow is mocked; tests cover loading / success / error states,
 * cell filtering + labelling, and every close affordance.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { CellTraceModal } from '../components/CellTraceModal';
import type { RawRowDetail } from '../types';

const mocks = vi.hoisted(() => ({ fetchRawRow: vi.fn() }));

vi.mock('../api', async (importOriginal) => {
  const mod = await importOriginal<typeof import('../api')>();
  return { ...mod, fetchRawRow: mocks.fetchRawRow };
});

afterEach(() => {
  vi.clearAllMocks();
});

const detail: RawRowDetail = {
  raw_row_id: 42,
  source_sheet_name: 'Power',
  excel_row_number: 17,
  raw_cells: { H: 'PWR-COAL-01', R: '1500', K: '2030', Z: '', AB: null as unknown as string },
  import_batch: {
    import_batch_id: 7,
    file_name: 'wp1_v3.xlsx',
    imported_at: '2026-07-01T10:00:00Z',
    note: 'baseline scenario',
  },
};

describe('CellTraceModal', () => {
  it('shows a loading state before data arrives', () => {
    mocks.fetchRawRow.mockReturnValue(new Promise(() => {}));
    render(<CellTraceModal rawRowId={42} onClose={() => {}} />);
    expect(screen.getByText(/Loading/)).toBeInTheDocument();
    expect(screen.getByText('raw_row_id = 42')).toBeInTheDocument();
  });

  it('renders sheet / row / batch metadata and labelled non-empty cells', async () => {
    mocks.fetchRawRow.mockResolvedValue(detail);
    render(<CellTraceModal rawRowId={42} onClose={() => {}} />);

    expect(await screen.findByText('Power')).toBeInTheDocument();
    expect(screen.getByText('Row 17')).toBeInTheDocument();
    expect(screen.getByText('wp1_v3.xlsx')).toBeInTheDocument();
    expect(screen.getByText('baseline scenario')).toBeInTheDocument();

    // Cells: labelled by canonical column
    expect(screen.getByText('PWR-COAL-01')).toBeInTheDocument();
    expect(screen.getByText('technology code')).toBeInTheDocument();
    expect(screen.getByText('capex')).toBeInTheDocument();
    // Empty / null cells are filtered out
    expect(screen.queryByText('efficiency')).not.toBeInTheDocument();
  });

  it('renders the error state when the fetch fails', async () => {
    mocks.fetchRawRow.mockRejectedValue(new Error('raw_row_id=42 does not exist'));
    render(<CellTraceModal rawRowId={42} onClose={() => {}} />);

    expect(await screen.findByText('Failed to load')).toBeInTheDocument();
    expect(screen.getByText(/does not exist/)).toBeInTheDocument();
  });

  it('closes via ×, footer button, backdrop click and Escape', async () => {
    mocks.fetchRawRow.mockResolvedValue(detail);
    const onClose = vi.fn();
    const { container } = render(<CellTraceModal rawRowId={42} onClose={onClose} />);
    await screen.findByText('Power');

    fireEvent.click(screen.getByLabelText('Close'));
    fireEvent.click(screen.getByText('Close'));
    fireEvent.click(container.querySelector('.modal-backdrop')!);
    fireEvent.keyDown(window, { key: 'Escape' });

    expect(onClose).toHaveBeenCalledTimes(4);
  });

  it('does not close when clicking inside the modal body', async () => {
    mocks.fetchRawRow.mockResolvedValue(detail);
    const onClose = vi.fn();
    render(<CellTraceModal rawRowId={42} onClose={onClose} />);

    fireEvent.click(await screen.findByText('Power'));
    expect(onClose).not.toHaveBeenCalled();
  });
});
