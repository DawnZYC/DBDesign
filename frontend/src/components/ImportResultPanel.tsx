import type { ImportResult } from '../types';

interface ImportResultPanelProps {
  result: ImportResult;
  onReviewConflicts?: () => void;
}

export function ImportResultPanel({ result, onReviewConflicts }: ImportResultPanelProps) {
  const importedAt = new Date(result.imported_at).toLocaleString('en-US');
  const hasPending = result.rows_pending > 0;

  return (
    <section className="result">
      <header className="result-header">
        <h2>Import Complete ✓</h2>
        <span className="batch-id">Batch #{result.import_batch_id}</span>
      </header>

      {hasPending && (
        <div className="pending-banner">
          <div>
            <strong>{result.rows_pending} rows</strong> were held for sector conflict review
          </div>
          {onReviewConflicts && (
            <button
              type="button"
              className="btn-primary"
              onClick={onReviewConflicts}
            >
              Review
            </button>
          )}
        </div>
      )}

      <dl className="result-meta">
        <div>
          <dt>File</dt>
          <dd>{result.file_name}</dd>
        </div>
        <div>
          <dt>Imported At</dt>
          <dd>{importedAt}</dd>
        </div>
        <div>
          <dt>Duration</dt>
          <dd>{(result.duration_ms / 1000).toFixed(2)} s</dd>
        </div>
        <div>
          <dt>Rows Imported</dt>
          <dd className="num-ok">{result.rows_imported.toLocaleString()}</dd>
        </div>
        <div>
          <dt>Rows Skipped</dt>
          <dd>{result.rows_skipped.toLocaleString()}</dd>
        </div>
        <div>
          <dt>Pending Review</dt>
          <dd className={hasPending ? 'num-warn' : ''}>
            {result.rows_pending.toLocaleString()}
          </dd>
        </div>
        <div>
          <dt>Quality Issues</dt>
          <dd className={result.issues > 0 ? 'num-warn' : ''}>
            {result.issues.toLocaleString()}
          </dd>
        </div>
      </dl>

      <table className="sheet-table">
        <thead>
          <tr>
            <th>Sheet</th>
            <th className="ralign">Total Rows</th>
            <th className="ralign">Imported</th>
            <th className="ralign">Skipped</th>
            <th className="ralign">Pending</th>
            <th className="ralign">Issues</th>
          </tr>
        </thead>
        <tbody>
          {result.sheets.map((s) => (
            <tr key={s.sheet_name}>
              <td>{s.sheet_name}</td>
              <td className="ralign">{s.rows_total}</td>
              <td className="ralign num-ok">{s.rows_imported}</td>
              <td className="ralign">{s.rows_skipped}</td>
              <td className={`ralign ${s.rows_pending > 0 ? 'num-warn' : ''}`}>
                {s.rows_pending}
              </td>
              <td className={`ralign ${s.issues > 0 ? 'num-warn' : ''}`}>{s.issues}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
