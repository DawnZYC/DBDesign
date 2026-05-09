import { useState } from 'react';
import { ConflictReviewModal } from './ConflictReviewModal';
import { FileUpload } from './FileUpload';
import { ImportResultPanel } from './ImportResultPanel';
import { SheetPicker } from './SheetPicker';
import { previewExcel, uploadExcel } from '../api';
import type { ConflictResolveResponse, FilePreview, ImportResult } from '../types';

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
      const selected = new Set(preview.sheets.filter((s) => s.is_known).map((s) => s.sheet_name));
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
      alert('Select at least one sheet');
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
        `Resolved ${response.resolved} rows; ${response.failed} rows failed: ${response.failure_reasons.join('; ')}`,
      );
    } else {
      setReviewMessage(`Resolved ${response.resolved} rows ✓`);
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
                Imported by <em>(optional)</em>
              </span>
              <input
                type="text"
                value={importedBy}
                onChange={(e) => setImportedBy(e.target.value)}
                placeholder="Example: zyc"
                disabled={isWorking}
              />
            </label>
            <label className="form-field">
              <span>
                Note <em>(optional)</em>
              </span>
              <input
                type="text"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Example: Power sheet sample row import"
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
            Reading the sheet list from <code>{stage.fileName}</code>...
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
              Choose Another File
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={handleImport}
              disabled={stage.selected.size === 0}
            >
              Import {stage.selected.size} Selected Sheets
            </button>
          </div>
        </>
      )}

      {stage.kind === 'importing' && (
        <section className="status uploading">
          <div className="spinner" aria-hidden="true" />
          <div>
            Importing {stage.sheetCount} sheets from <code>{stage.fileName}</code>...
          </div>
        </section>
      )}

      {stage.kind === 'error' && (
        <section className="status error">
          <strong>{stage.canRetry ? 'Preview failed' : 'Import failed'}</strong>
          <pre>{stage.message}</pre>
          <button type="button" onClick={handleReset}>
            Retry
          </button>
        </section>
      )}

      {stage.kind === 'success' && (
        <>
          <ImportResultPanel result={stage.result} onReviewConflicts={() => setReviewing(true)} />
          {reviewMessage && <div className="review-message">{reviewMessage}</div>}
          <button className="reset-btn" type="button" onClick={handleReset}>
            Import Another File
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
