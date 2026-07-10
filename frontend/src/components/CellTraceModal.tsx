/**
 * CellTraceModal — source-cell trace overlay (M4).
 *
 * Opens when the user clicks a chart data point; fetches the original Excel
 * row via GET /api/raw-rows/{id} and shows sheet / row number / raw_cells
 * JSONB / import batch info. Close: backdrop click, ×, or Escape.
 */
import { useEffect, useState } from 'react';

import { fetchRawRow } from '../api';
import type { RawRowDetail } from '../types';

interface Props {
  rawRowId: number;
  onClose: () => void;
}

type FetchState =
  | { status: 'loading' }
  | { status: 'ok'; data: RawRowDetail }
  | { status: 'error'; message: string };

export function CellTraceModal({ rawRowId, onClose }: Props) {
  const [state, setState] = useState<FetchState>({ status: 'loading' });

  // Fetch data.
  useEffect(() => {
    setState({ status: 'loading' });
    let cancelled = false;

    fetchRawRow(rawRowId)
      .then((data) => {
        if (!cancelled) setState({ status: 'ok', data });
      })
      .catch((err: Error) => {
        if (!cancelled) setState({ status: 'error', message: err.message });
      });

    return () => {
      cancelled = true;
    };
  }, [rawRowId]);

  // Close on Escape.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);

  return (
    <div
      className="modal-backdrop"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="modal" role="dialog" aria-modal="true">
        {/* Header */}
        <div className="modal-header">
          <div>
            <h2 className="modal-title" style={{ margin: 0, fontSize: 17 }}>
              Source cell trace
            </h2>
            <p className="modal-subtitle">raw_row_id = {rawRowId}</p>
          </div>
          <button type="button" className="modal-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>

        {/* Body */}
        <div className="modal-body">
          {state.status === 'loading' && (
            <div className="modal-empty">
              <span className="spinner" style={{ display: 'inline-block', marginRight: 8 }} />
              Loading…
            </div>
          )}

          {state.status === 'error' && (
            <div className="modal-error">
              <strong>Failed to load</strong>
              <pre>{state.message}</pre>
            </div>
          )}

          {state.status === 'ok' && <CellTraceContent data={state.data} />}
        </div>

        {/* Footer */}
        <div className="modal-footer">
          <span className="modal-meta">Click chart data points to trace their original source</span>
          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// Canonical EcoTEA column letter -> human field label (matches the importer's fixed layout).
const COLUMN_LABELS: Record<string, string> = {
  A: 'WP / sector',
  B: 'data owner',
  C: 'data provider',
  D: 'data source',
  E: 'data source description',
  F: 'data user',
  G: 'usage purpose',
  H: 'technology code',
  I: 'technology description',
  J: 'geography',
  K: 'year',
  L: 'start year',
  M: 'lifetime (yr)',
  N: 'grade',
  O: 'emission factor',
  P: 'emission factor unit',
  Q: 'base currency',
  R: 'capex',
  S: 'capex unit',
  T: 'fixed opex',
  U: 'fixed opex unit',
  V: 'variable opex',
  W: 'variable opex unit',
  X: 'tax cost',
  Y: 'subsidy cost',
  Z: 'efficiency',
  AA: 'technology efficiency',
  AB: 'commodity share',
  AC: 'commodity code',
  AD: 'commodity demand',
  AE: 'interpolation rule',
  AF: 'capacity-to-activity factor',
  AG: 'heat rate',
  AH: 'capacity',
  AI: 'capacity type',
  AJ: 'max import possible',
  AK: 'max solar output allowed',
  AL: 'capacity (special)',
};

/* ---- Body (rendered after data loads) ---- */
function CellTraceContent({ data }: { data: RawRowDetail }) {
  const { source_sheet_name, excel_row_number, raw_cells, import_batch } = data;

  // Non-empty cells, sorted by column (single letters before double).
  const cellEntries = Object.entries(raw_cells)
    .filter(([, v]) => v !== null && v !== '' && v !== undefined)
    .sort(([a], [b]) => (a.length - b.length || (a < b ? -1 : 1)));

  const importedAt = new Date(import_batch.imported_at).toLocaleString('en-US', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });

  return (
    <>
      {/* Excel location */}
      <div className="cell-trace-meta">
        <div className="cell-trace-meta-row">
          <dt>Sheet</dt>
          <dd>{source_sheet_name}</dd>
        </div>
        <div className="cell-trace-meta-row">
          <dt>Row</dt>
          <dd>Row {excel_row_number}</dd>
        </div>
        <div className="cell-trace-meta-row">
          <dt>Source file</dt>
          <dd>{import_batch.file_name}</dd>
        </div>
        <div className="cell-trace-meta-row">
          <dt>Imported at</dt>
          <dd>{importedAt}</dd>
        </div>
        {import_batch.note && (
          <div className="cell-trace-meta-row">
            <dt>Scenario note</dt>
            <dd>{import_batch.note}</dd>
          </div>
        )}
      </div>

      {/* Raw cell contents */}
      <div className="cell-trace-section-title">Source cells</div>
      <table className="cell-trace-table">
        <tbody>
          {cellEntries.map(([col, val]) => (
            <tr key={col}>
              <td className="cell-trace-col">{col}</td>
              <td className="cell-trace-label">{COLUMN_LABELS[col] ?? '—'}</td>
              <td className="cell-trace-val">{String(val)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
