import { useEffect, useState } from 'react';
import { conversionDownloadUrl, convertVT, listConvertModels } from '../api';
import { FileUpload } from './FileUpload';
import type { ConvertModelInfo, ConvertResult } from '../types';

interface ConvertViewProps {
  onHandoffToImport: (result: ConvertResult) => void;
}

type Stage =
  | { kind: 'idle' }
  | { kind: 'converting'; sourceName: string }
  | { kind: 'success'; result: ConvertResult }
  | { kind: 'error'; message: string };

const ACCEPTED_SUFFIXES = ['.xlsx', '.xlsm', '.xls'];

function isAcceptedFile(name: string): boolean {
  const lower = name.toLowerCase();
  return ACCEPTED_SUFFIXES.some((suffix) => lower.endsWith(suffix));
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export function ConvertView({ onHandoffToImport }: ConvertViewProps) {
  const [models, setModels] = useState<ConvertModelInfo[]>([]);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [selectedModel, setSelectedModel] = useState<string | null>(null);
  const [sourceFile, setSourceFile] = useState<File | null>(null);
  const [useCustomTemplate, setUseCustomTemplate] = useState(false);
  const [templateFile, setTemplateFile] = useState<File | null>(null);
  const [stage, setStage] = useState<Stage>({ kind: 'idle' });

  useEffect(() => {
    listConvertModels()
      .then((items) => {
        setModels(items);
        if (items.length > 0) {
          setSelectedModel(items[0].key);
        }
      })
      .catch((err) => setModelsError((err as Error).message));
  }, []);

  const isWorking = stage.kind === 'converting';

  const handleSourceSelect = (file: File) => {
    if (!isAcceptedFile(file.name)) {
      alert('Source file must be an Excel workbook (.xlsx, .xlsm, .xls).');
      return;
    }
    setSourceFile(file);
    setStage({ kind: 'idle' });
  };

  const handleTemplatePick = (file: File | undefined) => {
    if (!file) return;
    if (!isAcceptedFile(file.name)) {
      alert('Template file must be an Excel workbook (.xlsx, .xlsm, .xls).');
      return;
    }
    setTemplateFile(file);
  };

  const handleConvert = async () => {
    if (!selectedModel || !sourceFile) return;
    setStage({ kind: 'converting', sourceName: sourceFile.name });
    try {
      const result = await convertVT({
        modelKey: selectedModel,
        sourceFile,
        templateFile: useCustomTemplate ? templateFile ?? undefined : undefined,
      });
      setStage({ kind: 'success', result });
    } catch (err) {
      setStage({ kind: 'error', message: (err as Error).message });
    }
  };

  const handleReset = () => {
    setStage({ kind: 'idle' });
    setSourceFile(null);
  };

  const canConvert =
    !!selectedModel &&
    !!sourceFile &&
    (!useCustomTemplate || !!templateFile) &&
    !isWorking;

  return (
    <div className="convert-view">
      <section className="convert-card">
        <div className="convert-card-header">
          <h3 className="convert-card-title">Step 1 · Choose source model</h3>
          <span className="convert-card-meta">
            {models.length} {models.length === 1 ? 'model' : 'models'} available
          </span>
        </div>

        {modelsError && (
          <div className="status-error-message">
            Unable to load model list. {modelsError}
          </div>
        )}

        {models.length > 0 && (
          <div className="model-grid" role="radiogroup" aria-label="Source model">
            {models.map((m) => {
              const isActive = selectedModel === m.key;
              return (
                <button
                  key={m.key}
                  type="button"
                  role="radio"
                  aria-checked={isActive}
                  className={`model-option ${isActive ? 'active' : ''}`}
                  onClick={() => setSelectedModel(m.key)}
                  disabled={isWorking}
                >
                  <div className="model-option-top">
                    <span className="model-option-key">{m.key}</span>
                    <span className="model-option-sector">{m.sector}</span>
                  </div>
                  {m.description && (
                    <span className="model-option-description">{m.description}</span>
                  )}
                </button>
              );
            })}
          </div>
        )}
      </section>

      <section className="convert-card">
        <div className="convert-card-header">
          <h3 className="convert-card-title">Step 2 · Upload VT source workbook</h3>
          <span className="convert-card-meta">
            Excel workbook (.xlsx, .xlsm, .xls)
          </span>
        </div>

        {sourceFile ? (
          <div className="file-summary">
            <span className="file-summary-name">{sourceFile.name}</span>
            <span className="file-summary-size">{formatBytes(sourceFile.size)}</span>
            <button
              type="button"
              className="file-summary-clear"
              onClick={() => setSourceFile(null)}
              disabled={isWorking}
            >
              Replace
            </button>
          </div>
        ) : (
          <FileUpload onFileSelected={handleSourceSelect} disabled={isWorking} />
        )}
      </section>

      <section className="convert-card">
        <div className="convert-card-header">
          <h3 className="convert-card-title">Step 3 · EcoTEA template</h3>
          <span className="convert-card-meta">
            {useCustomTemplate ? 'Custom template' : 'Bundled template (default)'}
          </span>
        </div>

        <label className="template-toggle">
          <input
            type="checkbox"
            checked={useCustomTemplate}
            onChange={(e) => {
              setUseCustomTemplate(e.target.checked);
              if (!e.target.checked) setTemplateFile(null);
            }}
            disabled={isWorking}
          />
          Use a custom EcoTEA template instead of the bundled one
        </label>

        {useCustomTemplate &&
          (templateFile ? (
            <div className="file-summary">
              <span className="file-summary-name">{templateFile.name}</span>
              <span className="file-summary-size">{formatBytes(templateFile.size)}</span>
              <button
                type="button"
                className="file-summary-clear"
                onClick={() => setTemplateFile(null)}
                disabled={isWorking}
              >
                Replace
              </button>
            </div>
          ) : (
            <TemplatePicker onPick={handleTemplatePick} disabled={isWorking} />
          ))}
      </section>

      {stage.kind === 'converting' && (
        <section className="status uploading">
          <div className="spinner" aria-hidden="true" />
          <div>
            Converting <code>{stage.sourceName}</code>
          </div>
        </section>
      )}

      {stage.kind === 'error' && (
        <section className="status error">
          <strong>Conversion failed</strong>
          <p className="status-error-message">{stage.message}</p>
          <button type="button" onClick={handleReset}>
            Try again
          </button>
        </section>
      )}

      {stage.kind === 'success' && (
        <ConvertSuccessPanel
          result={stage.result}
          onHandoffToImport={() => onHandoffToImport(stage.result)}
          onReset={handleReset}
        />
      )}

      {stage.kind !== 'success' && (
        <div className="action-row">
          <button
            type="button"
            className="btn-primary"
            onClick={handleConvert}
            disabled={!canConvert}
          >
            Convert workbook
          </button>
        </div>
      )}
    </div>
  );
}

function ConvertSuccessPanel({
  result,
  onHandoffToImport,
  onReset,
}: {
  result: ConvertResult;
  onHandoffToImport: () => void;
  onReset: () => void;
}) {
  const downloadHref = conversionDownloadUrl(result.download_token);
  return (
    <section className="convert-success">
      <h3 className="convert-success-title">Conversion complete</h3>

      <dl className="convert-success-meta">
        <div>
          <dt>Output file</dt>
          <dd>{result.download_name}</dd>
        </div>
        <div>
          <dt>Sheet</dt>
          <dd>{result.sheet_name}</dd>
        </div>
        <div>
          <dt>Rows produced</dt>
          <dd>{result.row_count.toLocaleString()}</dd>
        </div>
        <div>
          <dt>Size</dt>
          <dd>{formatBytes(result.bytes)}</dd>
        </div>
      </dl>

      <div className="convert-success-actions">
        <button type="button" className="btn-primary" onClick={onHandoffToImport}>
          Send to import
        </button>
        <a className="btn-secondary" href={downloadHref} download={result.download_name}>
          Download workbook
        </a>
        <button type="button" className="btn-ghost" onClick={onReset}>
          Convert another file
        </button>
      </div>
    </section>
  );
}

function TemplatePicker({
  onPick,
  disabled,
}: {
  onPick: (file: File | undefined) => void;
  disabled: boolean;
}) {
  return (
    <FileUpload onFileSelected={(file) => onPick(file)} disabled={disabled} />
  );
}
