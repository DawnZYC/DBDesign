import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { SheetPicker } from '../components/SheetPicker';
import type { SheetPreview } from '../types';

const sheets: SheetPreview[] = [
  { sheet_name: 'ELEC', is_known: true,  sector_code: 'ELEC',  data_rows: 100 },
  { sheet_name: 'TRANS', is_known: true, sector_code: 'TRANS', data_rows: 50  },
  { sheet_name: 'NOTES', is_known: false, sector_code: null,   data_rows: 0   },
];

function renderPicker(selected: Set<string>, onChange = vi.fn()) {
  return { onChange, ...render(
    <SheetPicker
      fileName="test.xlsx"
      sheets={sheets}
      selected={selected}
      onChange={onChange}
    />,
  )};
}

describe('SheetPicker', () => {
  it('renders the file name and recognized-sheet count', () => {
    renderPicker(new Set());
    expect(screen.getByText('test.xlsx')).toBeInTheDocument();
    expect(screen.getByText(/2 recognized of 3 sheets/i)).toBeInTheDocument();
  });

  it('renders all sheet names', () => {
    renderPicker(new Set());
    // ELEC and TRANS each appear twice (sheet_name + sector_code); use getAllByText
    expect(screen.getAllByText('ELEC').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('TRANS').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('NOTES')).toBeInTheDocument();
  });

  it('shows the row count for each sheet', () => {
    renderPicker(new Set());
    expect(screen.getByText('100 data rows')).toBeInTheDocument();
    expect(screen.getByText('50 data rows')).toBeInTheDocument();
    expect(screen.getByText('0 data rows')).toBeInTheDocument();
  });

  it('marks unrecognized sheets with an "Unrecognized" badge', () => {
    renderPicker(new Set());
    expect(screen.getByText('Unrecognized')).toBeInTheDocument();
  });

  it('disables the checkbox for unrecognized sheets', () => {
    renderPicker(new Set());
    // Checkbox order: [0]=select-all, [1]=ELEC, [2]=TRANS, [3]=NOTES
    const checkboxes = screen.getAllByRole('checkbox');
    expect(checkboxes[3]).toBeDisabled();
  });

  it('reflects pre-selected sheets as checked', () => {
    renderPicker(new Set(['ELEC']));
    const checkboxes = screen.getAllByRole('checkbox');
    expect(checkboxes[1]).toBeChecked();   // ELEC
    expect(checkboxes[2]).not.toBeChecked(); // TRANS
  });

  it('calls onChange with the sheet added when an unchecked known sheet is toggled', () => {
    const { onChange } = renderPicker(new Set(['ELEC']));
    const checkboxes = screen.getAllByRole('checkbox');
    fireEvent.click(checkboxes[2]); // toggle TRANS in
    const result = onChange.mock.calls[0][0] as Set<string>;
    expect(result.has('TRANS')).toBe(true);
    expect(result.has('ELEC')).toBe(true);
  });

  it('calls onChange with the sheet removed when a checked sheet is toggled off', () => {
    const { onChange } = renderPicker(new Set(['ELEC', 'TRANS']));
    const checkboxes = screen.getAllByRole('checkbox');
    fireEvent.click(checkboxes[1]); // toggle ELEC off
    const result = onChange.mock.calls[0][0] as Set<string>;
    expect(result.has('ELEC')).toBe(false);
    expect(result.has('TRANS')).toBe(true);
  });

  it('"Select all recognized" selects all known sheets when none are selected', () => {
    const { onChange } = renderPicker(new Set());
    const selectAll = screen.getByRole('checkbox', { name: /select all recognized/i });
    fireEvent.click(selectAll);
    const result = onChange.mock.calls[0][0] as Set<string>;
    expect(result.has('ELEC')).toBe(true);
    expect(result.has('TRANS')).toBe(true);
    expect(result.has('NOTES')).toBe(false);
  });

  it('"Select all recognized" deselects all known sheets when all are already selected', () => {
    const { onChange } = renderPicker(new Set(['ELEC', 'TRANS']));
    const selectAll = screen.getByRole('checkbox', { name: /select all recognized/i });
    expect(selectAll).toBeChecked();
    fireEvent.click(selectAll);
    const result = onChange.mock.calls[0][0] as Set<string>;
    expect(result.size).toBe(0);
  });

  it('disables all checkboxes when the disabled prop is true', () => {
    render(
      <SheetPicker
        fileName="test.xlsx"
        sheets={sheets}
        selected={new Set()}
        onChange={vi.fn()}
        disabled
      />,
    );
    screen.getAllByRole('checkbox').forEach((cb) => expect(cb).toBeDisabled());
  });
});
