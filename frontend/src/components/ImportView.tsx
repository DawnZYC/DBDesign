import { useEffect, useRef, useState } from 'react';
import { ConflictReviewModal } from './ConflictReviewModal';
import { FileUpload } from './FileUpload';
import { ImportResultPanel } from './ImportResultPanel';
import { SheetPicker } from './SheetPicker';
import { importFromConversion, previewExcel, previewFromConversion, uploadExcel } from '../api';
import type { ConflictResolveResponse, ConvertResult, FilePreview, ImportResult } from '../types';

type Source = { kind: 'file'; file: File } | { kind: 'token'; token: string; fileName: string };

type Stage =
  | { kind: 'idle' }
  | { kind: 'previewing'; fileName: string }
  | { kind: 'picking'; source: Source; preview: FilePreview; selected: Set<string> }
  | { kind: 'importing'; fileName: string; sheetCount: number }
  | { kind: 'success'; result: ImportResult }
  | { kind: 'error'; message: string; canRetry: boolean };

interface ImportViewProps {
  /** Optional pre-converted file handed over from the Convert step. */
  handoff?: ConvertResult | null;
  /** Called once the handoff has been consumed (so the parent can clear it). */
  onHandoffConsumed?: () => void;
}

export function ImportView({ handoff, onHandoffConsumed }: ImportViewProps) {
  const [stage, setStage] = useState<Stage>({ kind: 'idle' });
  const [importedBy, setImportedBy] = useState('');
  const [note, setNote] = useState('');
  const [reviewing, setReviewing] = useState(false);
  const [reviewMessage, setReviewMessage] = useState<string | null>(null);
  const consumedTokens = useRef<Set<string>>(new Set());

  const beginPreviewFromToken = async (token: string, fileName: string, defaultNote?: string) => {
    setStage({ kind: 'previewing', fileName });
    try {
      const preview = await previewFromConversion(token);
      const selected = new Set(preview.sheets.filter((s) => s.is_known).map((s) => s.sheet_name));
      setStage({
        kind: 'picking',
        source: { kind: 'token', token, fileName },
        preview,
        selected,
      });
      if (defaultNote && !note.trim()) {
        setNote(defaultNote);
      }
    } catch (err) {
      setStage({
        kind: 'error',
        message: (err as Error).message,
        canRetry: true,
      });
    }
  };

  // Consume an incoming handoff exactly once.
  useEffect(() => {
    if (!handoff) return;
    if (consumedTokens.current.has(handoff.download_token)) return;
    consumedTokens.current.add(handoff.download_token);
    void beginPreviewFromToken(
      handoff.download_token,
      handoff.download_name,
      `Converted from ${handoff.source_file_name} (${handoff.model_key})`,
    );
    onHandoffConsumed?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [handoff]);

  const handleFile = async (file: File) => {
    setStage({ kind: 'previewing', fileName: file.name });
    try {
      const preview = await previewExcel(file);
      const selected = new Set(preview.sheets.filter((s) => s.is_known).map((s) => s.sheet_name));
      setStage({
        kind: 'picking',
        source: { kind: 'file', file },
        preview,
        selected,
      });
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

    const fileName = stage.source.kind === 'file' ? stage.source.file.name : stage.source.fileName;

    setStage({
      kind: 'importing',
      fileName,
      sheetCount: stage.selected.size,
    });

    try {
      const sheets = Array.from(stage.selected);
      const result =
        stage.source.kind === 'file'
          ? await uploadExcel(stage.source.file, {
              importedBy: importedBy.trim() || undefined,
              note: note.trim() || undefined,
              sheets,
            })
          : await importFromConversion({
              token: stage.source.token,
              importedBy: importedBy.trim() || undefined,
              note: note.trim() || undefined,
              sheets,
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
      setReviewMessage(`Resolved ${response.resolved} rows successfully.`);
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
  const showHandoffBanner = stage.kind === 'picking' && stage.source.kind === 'token';

  return (
    <div className="import-view">
      {showHandoffBanner && stage.kind === 'picking' && stage.source.kind === 'token' && (
        <div className="handoff-banner">
          <div>
            <strong>Loaded from Convert step.</strong>{' '}
            <span className="handoff-banner-meta">File: {stage.source.fileName}</span>
          </div>
          <button type="button" className="handoff-banner-clear" onClick={handleReset}>
            Use a different file
          </button>
        </div>
      )}

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
                placeholder="Your name"
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
                placeholder="Brief description of this batch"
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
            Reading the sheet list from <code>{stage.fileName}</code>
          </div>
        </section>
      )}

      {stage.kind === 'picking' && (
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
                placeholder="Your name"
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
                placeholder="Brief description of this batch"
                disabled={isWorking}
              />
            </label>
          </section>
          <SheetPicker
            fileName={stage.preview.file_name}
            sheets={stage.preview.sheets}
            selected={stage.selected}
            onChange={handleSelectionChange}
          />
          <div className="action-row">
            <button type="button" className="btn-secondary" onClick={handleReset}>
              Choose another file
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={handleImport}
              disabled={stage.selected.size === 0}
            >
              Import {stage.selected.size} selected sheet{stage.selected.size === 1 ? '' : 's'}
            </button>
          </div>
        </>
      )}

      {stage.kind === 'importing' && (
        <section className="status uploading">
          <div className="spinner" aria-hidden="true" />
          <div>
            Importing {stage.sheetCount} sheets from <code>{stage.fileName}</code>
          </div>
        </section>
      )}

      {stage.kind === 'error' && (
        <section className="status error">
          <strong>{stage.canRetry ? 'Preview failed' : 'Import failed'}</strong>
          <p className="status-error-message">{stage.message}</p>
          <button type="button" onClick={handleReset}>
            Try again
          </button>
        </section>
      )}

      {stage.kind === 'success' && (
        <>
          <ImportResultPanel result={stage.result} onReviewConflicts={() => setReviewing(true)} />
          {reviewMessage && <div className="review-message">{reviewMessage}</div>}
          <button className="reset-btn" type="button" onClick={handleReset}>
            Import another file
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
