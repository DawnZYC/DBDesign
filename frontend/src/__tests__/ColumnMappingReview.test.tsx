/**
 * ColumnMappingReview — M5 column-alignment review tests.
 *
 * Covers: prefill from suggestions (auto/review vs unmatched), override
 * emission, duplicate-target conflict detection/exclusion, and re-init when a
 * new file's mappings arrive.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ColumnMappingReview } from '../components/ColumnMappingReview';
import type { ColumnSuggestion, SheetColumnMapping, StandardFieldInfo } from '../types';

const standardFields: StandardFieldInfo[] = [
  { column: 'H', field: 'technology_code', label: 'technology/process' },
  { column: 'K', field: 'data_year', label: 'year of data' },
  { column: 'R', field: 'capex', label: 'capex' },
] as StandardFieldInfo[];

function suggestion(overrides: Partial<ColumnSuggestion>): ColumnSuggestion {
  return {
    excel_column: 'S',
    excel_header: 'build cost',
    target_column: 'R',
    target_field: 'capex',
    confidence: 0.95,
    status: 'auto',
    reasoning: 'alias match',
    ...overrides,
  };
}

function mapping(overrides: Partial<SheetColumnMapping> = {}): SheetColumnMapping {
  return {
    sheet_name: 'Power',
    layout_is_standard: false,
    auto_count: 1,
    review_count: 0,
    unmatched_count: 0,
    suggestions: [suggestion({})],
    ...overrides,
  } as SheetColumnMapping;
}

describe('ColumnMappingReview', () => {
  it('renders nothing when no mappings are provided', () => {
    const { container } = render(
      <ColumnMappingReview mappings={[]} standardFields={standardFields} onChange={() => {}} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('prefills auto suggestions and emits them as overrides', () => {
    const onChange = vi.fn();
    render(
      <ColumnMappingReview
        mappings={[mapping()]}
        standardFields={standardFields}
        onChange={onChange}
      />,
    );

    expect(screen.getByText('1 auto')).toBeInTheDocument();
    expect(screen.getByRole('combobox')).toHaveValue('R');
    expect(onChange).toHaveBeenLastCalledWith({ Power: { S: 'R' } });
  });

  it('defaults unmatched columns to "do not import"', () => {
    const onChange = vi.fn();
    render(
      <ColumnMappingReview
        mappings={[
          mapping({
            unmatched_count: 1,
            auto_count: 0,
            suggestions: [
              suggestion({ status: 'unmatched', target_column: null, target_field: null }),
            ],
          }),
        ]}
        standardFields={standardFields}
        onChange={onChange}
      />,
    );

    expect(screen.getByText('1 unmatched')).toBeInTheDocument();
    expect(screen.getByRole('combobox')).toHaveValue('__none__');
    expect(onChange).toHaveBeenLastCalledWith({});
    expect(screen.getByText('—')).toBeInTheDocument(); // confidence placeholder
  });

  it('lets the user re-target a column and emits the updated override', () => {
    const onChange = vi.fn();
    render(
      <ColumnMappingReview
        mappings={[mapping({ review_count: 1 })]}
        standardFields={standardFields}
        onChange={onChange}
      />,
    );

    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'K' } });
    expect(onChange).toHaveBeenLastCalledWith({ Power: { S: 'K' } });
    expect(screen.getByText(/low confidence/)).toBeInTheDocument();
  });

  it('flags duplicate targets, excludes them from overrides, and reports conflicts', () => {
    const onChange = vi.fn();
    const onConflictsChange = vi.fn();
    render(
      <ColumnMappingReview
        mappings={[
          mapping({
            auto_count: 2,
            suggestions: [
              suggestion({ excel_column: 'S' }),
              suggestion({ excel_column: 'T', excel_header: 'capital expenditure' }),
            ],
          }),
        ]}
        standardFields={standardFields}
        onChange={onChange}
        onConflictsChange={onConflictsChange}
      />,
    );

    // Both S and T map to R -> conflict banner, tags, nothing applied for them.
    expect(screen.getByText(/mapped from more than one column/)).toBeInTheDocument();
    expect(screen.getAllByText('duplicate target')).toHaveLength(2);
    expect(onChange).toHaveBeenLastCalledWith({});
    expect(onConflictsChange).toHaveBeenLastCalledWith(true);

    // Resolving the conflict re-applies both mappings.
    fireEvent.change(screen.getAllByRole('combobox')[1], { target: { value: 'K' } });
    expect(onChange).toHaveBeenLastCalledWith({ Power: { S: 'R', T: 'K' } });
    expect(onConflictsChange).toHaveBeenLastCalledWith(false);
  });

  it('re-initializes selections when a new file (different mappings) arrives', () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <ColumnMappingReview
        mappings={[mapping()]}
        standardFields={standardFields}
        onChange={onChange}
      />,
    );
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'H' } });
    expect(onChange).toHaveBeenLastCalledWith({ Power: { S: 'H' } });

    rerender(
      <ColumnMappingReview
        mappings={[
          mapping({
            sheet_name: 'Industry',
            suggestions: [suggestion({ excel_column: 'Q' })],
          }),
        ]}
        standardFields={standardFields}
        onChange={onChange}
      />,
    );
    // Fresh prefill from the new suggestions, not the old user edit.
    expect(screen.getByRole('combobox')).toHaveValue('R');
    expect(onChange).toHaveBeenLastCalledWith({ Industry: { Q: 'R' } });
  });
});
