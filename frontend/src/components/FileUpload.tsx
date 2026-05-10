import { useCallback, useRef, useState, type ChangeEvent, type DragEvent } from 'react';

interface FileUploadProps {
  onFileSelected: (file: File) => void;
  disabled?: boolean;
}

const ACCEPT = '.xlsx,.xlsm';

export function FileUpload({ onFileSelected, disabled = false }: FileUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);

  const handleSelect = useCallback(
    (file: File | undefined) => {
      if (!file) return;
      const lower = file.name.toLowerCase();
      if (!lower.endsWith('.xlsx') && !lower.endsWith('.xlsm')) {
        alert('Only .xlsx / .xlsm files are supported');
        return;
      }
      onFileSelected(file);
    },
    [onFileSelected],
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
      role="button"
      tabIndex={0}
      aria-label="Select or drop an Excel file"
    >
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
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
      <div className="drop-hint">Excel workbook (.xlsx or .xlsm), up to 50&nbsp;MB</div>
    </div>
  );
}
