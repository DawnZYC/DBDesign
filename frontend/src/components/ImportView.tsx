import { useState } from 'react';
import { ConflictReviewModal } from './ConflictReviewModal';
import { FileUpload } from './FileUpload';
import { ImportResultPanel } from './ImportResultPanel';
import { SheetPicker } from './SheetPicker';
import { previewExcel, uploadExcel } from '../api';
import type {
  ConflictResolveResponse,
  FilePreview,
  ImportResult,
} from '../types';

type Stage =
  | { kind: 'idle' }
  | { kind: 'previewing'; fileName: string }
  | { kind: 'picking'; file: File; preview: FilePreview; selected: Set<string> }
  | { kind: 'importing'; fileName: string; sheetCount: number }
  | { kind: 'success'; result: ImportResult }
  | { kind: 'error'; message: string; canRetry: boolean };

export function ImportView() {
  const [stage, setStage] = useState<Stage>({ kind: 'idle' });
  const [importedBy, setImportedBy] = useState('');
  const [note, setNote] = useState('');
  const [reviewing, setReviewing] = useState(false);
  const [reviewMessage, setReviewMessage] = useState<string | null>(null);

  const handleFile = async (file: File) => {
    setStage({ kind: 'previewing', fileName: file.name });
    try {
      const preview = await previewExcel(file);
      const selected = new Set(
        preview.sheets.filter((s) => s.is_known).map((s) => s.sheet_name),
      );
      setStage({ kind: 'picking', file, preview, selected });
    } catch (err) {
      setStage({
        kind: 'error',
        message: (err as Error).message,
        canRetry: true,
      });
    }
  };

  const handleSelectionChange = (selected: Set<string>) => {
    setStage((prev) => (prev.kind === 'picking' ? { ...prev, selected } : prev));
  };

  const handleImport = async () => {
    if (stage.kind !== 'picking') return;
    if (stage.selected.size === 0) {
      alert('请至少选择一个 sheet');
      return;
    }

    setStage({
      kind: 'importing',
      fileName: stage.file.name,
      sheetCount: stage.selected.size,
    });
    try {
      const result = await uploadExcel(stage.file, {
        importedBy: importedBy.trim() || undefined,
        note: note.trim() || undefined,
        sheets: Array.from(stage.selected),
      });
      setStage({ kind: 'success', result });
    } catch (err) {
      setStage({
        kind: 'error',
        message: (err as Error).message,
        canRetry: false,
      });
    }
  };

  const handleReset = () => {
    setStage({ kind: 'idle' });
    setReviewMessage(null);
  };

  const handleReviewResolved = (response: ConflictResolveResponse) => {
    setReviewing(false);
    if (response.failed > 0) {
      setReviewMessage(
        `已处理 ${response.resolved} 行，${response.failed} 行失败：${response.failure_reasons.join('; ')}`,
      );
    } else {
      setReviewMessage(`已处理 ${response.resolved} 行 ✓`);
    }
    if (stage.kind === 'success') {
      const newPending = Math.max(stage.result.rows_pending - response.resolved, 0);
      setStage({
        kind: 'success',
        result: {
          ...stage.result,
          rows_pending: newPending,
          rows_imported: stage.result.rows_imported + response.resolved,
        },
      });
    }
  };

  const isWorking = stage.kind === 'previewing' || stage.kind === 'importing';

  return (
    <div className="import-view">
      {(stage.kind === 'idle' || stage.kind === 'previewing') && (
        <>
          <section className="form-row">
            <label className="form-field">
              <span>
                导入操作人 <em>(可选)</em>
              </span>
              <input
                type="text"
                value={importedBy}
                onChange={(e) => setImportedBy(e.target.value)}
                placeholder="例如：zyc"
                disabled={isWorking}
              />
            </label>
            <label className="form-field">
              <span>
                本次备注 <em>(可选)</em>
              </span>
              <input
                type="text"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="例如：Power sheet sample row import"
                disabled={isWorking}
              />
            </label>
          </section>
          <FileUpload onFileSelected={handleFile} disabled={isWorking} />
        </>
      )}

      {stage.kind === 'previewing' && (
        <section className="status uploading">
          <div className="spinner" aria-hidden="true" />
          <div>
            正在读取 <code>{stage.fileName}</code> 的 sheet 列表 ……
          </div>
        </section>
      )}

      {stage.kind === 'picking' && (
        <>
          <SheetPicker
            fileName={stage.preview.file_name}
            sheets={stage.preview.sheets}
            selected={stage.selected}
            onChange={handleSelectionChange}
          />
          <div className="action-row">
            <button type="button" className="btn-secondary" onClick={handleReset}>
              重新选择文件
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={handleImport}
              disabled={stage.selected.size === 0}
            >
              导入选中的 {stage.selected.size} 个 sheet
            </button>
          </div>
        </>
      )}

      {stage.kind === 'importing' && (
        <section className="status uploading">
          <div className="spinner" aria-hidden="true" />
          <div>
            正在导入 <code>{stage.fileName}</code> 的 {stage.sheetCount} 个 sheet ……
          </div>
        </section>
      )}

      {stage.kind === 'error' && (
        <section className="status error">
          <strong>{stage.canRetry ? '预览失败' : '导入失败'}</strong>
          <pre>{stage.message}</pre>
          <button type="button" onClick={handleReset}>
            重试
          </button>
        </section>
      )}

      {stage.kind === 'success' && (
        <>
          <ImportResultPanel
            result={stage.result}
            onReviewConflicts={() => setReviewing(true)}
          />
          {reviewMessage && <div className="review-message">{reviewMessage}</div>}
          <button className="reset-btn" type="button" onClick={handleReset}>
            再导入一份
          </button>
        </>
      )}

      {reviewing && (
        <ConflictReviewModal
          onClose={() => setReviewing(false)}
          onResolved={handleReviewResolved}
        />
      )}
    </div>
  );
}
