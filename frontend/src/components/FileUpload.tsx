import { useCallback, useRef, useState, type ChangeEvent, type DragEvent } from 'react';

interface FileUploadProps {
  onFileSelected: (file: File) => void;
  disabled?: boolean;
  /** Accepted file suffixes (lowercase, with dot). Defaults to the importer's .xlsx/.xlsm. */
  acceptSuffixes?: string[];
}

const DEFAULT_SUFFIXES = ['.xlsx', '.xlsm'];

export function FileUpload({
  onFileSelected,
  disabled = false,
  acceptSuffixes = DEFAULT_SUFFIXES,
}: FileUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const accept = acceptSuffixes.join(',');
  const suffixHint = acceptSuffixes.join(' / ');

  const handleSelect = useCallback(
    (file: File | undefined) => {
      if (!file) return;
      const lower = file.name.toLowerCase();
      if (!acceptSuffixes.some((s) => lower.endsWith(s))) {
        alert(`Only ${suffixHint} files are supported`);
        return;
      }
      onFileSelected(file);
    },
    [onFileSelected, acceptSuffixes, suffixHint],
  );

  const handleChange = (event: ChangeEvent<HTMLInputElement>) => {
    handleSelect(event.target.files?.[0]);
    event.target.value = ''; // Allow selecting the same file again.
  };

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragOver(false);
    if (disabled) return;
    handleSelect(event.dataTransfer.files?.[0]);
  };

  return (
    <div
      className={`drop-zone ${dragOver ? 'drag-over' : ''} ${disabled ? 'disabled' : ''}`}
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
      onClick={() => !disabled && inputRef.current?.click()}
      onKeyDown={(e) => {
        if ((e.key === 'Enter' || e.key === ' ') && !disabled) {
          e.preventDefault();
          inputRef.current?.click();
        }
      }}
      role="button"
      tabIndex={0}
      aria-label="Select or drop an Excel file"
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        onChange={handleChange}
        disabled={disabled}
        hidden
      />
      <div className="drop-icon" aria-hidden="true">
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M12 16V4" />
          <path d="M7 9l5-5 5 5" />
          <path d="M5 20h14" />
        </svg>
      </div>
      <div className="drop-text">
        <strong>Click to choose a file</strong> or drag it here
      </div>
      <div className="drop-hint">Excel workbook ({suffixHint}), up to 50&nbsp;MB</div>
    </div>
  );
}
