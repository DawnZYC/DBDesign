import type { ImportResult } from '../types';

interface ImportResultPanelProps {
  result: ImportResult;
  onReviewConflicts?: () => void;
}

export function ImportResultPanel({ result, onReviewConflicts }: ImportResultPanelProps) {
  const importedAt = new Date(result.imported_at).toLocaleString('zh-CN');
  const hasPending = result.rows_pending > 0;

  return (
    <section className="result">
      <header className="result-header">
        <h2>导入完成 ✓</h2>
        <span className="batch-id">批次 #{result.import_batch_id}</span>
      </header>

      {hasPending && (
        <div className="pending-banner">
          <div>
            <strong>{result.rows_pending} 行</strong> 因 sector 冲突暂未入库，需要您手动确认
          </div>
          {onReviewConflicts && (
            <button
              type="button"
              className="btn-primary"
              onClick={onReviewConflicts}
            >
              去复核
            </button>
          )}
        </div>
      )}

      <dl className="result-meta">
        <div>
          <dt>文件</dt>
          <dd>{result.file_name}</dd>
        </div>
        <div>
          <dt>导入时间</dt>
          <dd>{importedAt}</dd>
        </div>
        <div>
          <dt>耗时</dt>
          <dd>{(result.duration_ms / 1000).toFixed(2)} s</dd>
        </div>
        <div>
          <dt>成功行数</dt>
          <dd className="num-ok">{result.rows_imported.toLocaleString()}</dd>
        </div>
        <div>
          <dt>跳过行数</dt>
          <dd>{result.rows_skipped.toLocaleString()}</dd>
        </div>
        <div>
          <dt>待复核</dt>
          <dd className={hasPending ? 'num-warn' : ''}>
            {result.rows_pending.toLocaleString()}
          </dd>
        </div>
        <div>
          <dt>异常追踪</dt>
          <dd className={result.issues > 0 ? 'num-warn' : ''}>
            {result.issues.toLocaleString()}
          </dd>
        </div>
      </dl>

      <table className="sheet-table">
        <thead>
          <tr>
            <th>Sheet</th>
            <th className="ralign">总数据行</th>
            <th className="ralign">已导入</th>
            <th className="ralign">已跳过</th>
            <th className="ralign">待复核</th>
            <th className="ralign">异常</th>
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
