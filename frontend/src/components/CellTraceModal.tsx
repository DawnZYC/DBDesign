/**
 * CellTraceModal — 源单元格反查浮层（M4）。
 *
 * 当用户点击 ECharts 图表上的数据点时打开，
 * 调用 GET /api/raw-rows/{id} 拉取该数据点对应的原始 Excel 行，
 * 展示：来源 sheet / 行号 / raw_cells JSONB / import_batch 信息。
 *
 * 关闭方式：点击遮罩 | 点击 × 按钮 | 按 Escape。
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

  // 拉取数据
  useEffect(() => {
    setState({ status: 'loading' });
    let cancelled = false;

    fetchRawRow(rawRowId)
      .then((data) => {
        if (!cancelled) setState({ status: 'ok', data });
      })
      .catch((err: Error) => {
        if (!cancelled)
          setState({ status: 'error', message: err.message });
      });

    return () => {
      cancelled = true;
    };
  }, [rawRowId]);

  // Escape 关闭
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
              源单元格追溯
            </h2>
            <p className="modal-subtitle">
              raw_row_id = {rawRowId}
            </p>
          </div>
          <button
            type="button"
            className="modal-close"
            onClick={onClose}
            aria-label="关闭"
          >
            ×
          </button>
        </div>

        {/* Body */}
        <div className="modal-body">
          {state.status === 'loading' && (
            <div className="modal-empty">
              <span className="spinner" style={{ display: 'inline-block', marginRight: 8 }} />
              加载中…
            </div>
          )}

          {state.status === 'error' && (
            <div className="modal-error">
              <strong>加载失败</strong>
              <pre>{state.message}</pre>
            </div>
          )}

          {state.status === 'ok' && <CellTraceContent data={state.data} />}
        </div>

        {/* Footer */}
        <div className="modal-footer">
          <span className="modal-meta">点击图表数据点可追溯原始数据来源</span>
          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>
              关闭
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ---- 内容区域（数据加载成功后渲染） ---- */
function CellTraceContent({ data }: { data: RawRowDetail }) {
  const { source_sheet_name, excel_row_number, raw_cells, import_batch } = data;

  // 把 raw_cells 格式化为可读的 JSON，每个 key 一行
  const cellsJson = JSON.stringify(raw_cells, null, 2);

  const importedAt = new Date(import_batch.imported_at).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });

  return (
    <>
      {/* Excel 位置信息 */}
      <div className="cell-trace-meta">
        <div className="cell-trace-meta-row">
          <dt>Sheet</dt>
          <dd>{source_sheet_name}</dd>
        </div>
        <div className="cell-trace-meta-row">
          <dt>行号</dt>
          <dd>第 {excel_row_number} 行</dd>
        </div>
        <div className="cell-trace-meta-row">
          <dt>来源文件</dt>
          <dd>{import_batch.file_name}</dd>
        </div>
        <div className="cell-trace-meta-row">
          <dt>导入时间</dt>
          <dd>{importedAt}</dd>
        </div>
        {import_batch.note && (
          <div className="cell-trace-meta-row">
            <dt>情景注记</dt>
            <dd>{import_batch.note}</dd>
          </div>
        )}
      </div>

      {/* 原始单元格内容 */}
      <div className="cell-trace-section-title">原始单元格（raw_cells）</div>
      <pre className="cell-trace-raw">{cellsJson}</pre>
    </>
  );
}
