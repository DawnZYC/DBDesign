import { useMemo } from 'react';
import type { SheetPreview } from '../types';

interface SheetPickerProps {
  fileName: string;
  sheets: SheetPreview[];
  selected: Set<string>;
  onChange: (selected: Set<string>) => void;
  disabled?: boolean;
}

export function SheetPicker({
  fileName,
  sheets,
  selected,
  onChange,
  disabled = false,
}: SheetPickerProps) {
  const knownSheets = useMemo(() => sheets.filter((s) => s.is_known), [sheets]);
  const allKnownSelected =
    knownSheets.length > 0 && knownSheets.every((s) => selected.has(s.sheet_name));

  const toggle = (sheetName: string) => {
    const next = new Set(selected);
    if (next.has(sheetName)) {
      next.delete(sheetName);
    } else {
      next.add(sheetName);
    }
    onChange(next);
  };

  const toggleAll = () => {
    if (allKnownSelected) {
      onChange(new Set());
    } else {
      onChange(new Set(knownSheets.map((s) => s.sheet_name)));
    }
  };

  return (
    <section className="sheet-picker">
      <header className="sheet-picker-header">
        <div>
          <strong>{fileName}</strong>
          <span className="sheet-picker-meta">
            {knownSheets.length} recognized of {sheets.length} sheets
          </span>
        </div>
        <label className="select-all">
          <input
            type="checkbox"
            checked={allKnownSelected}
            onChange={toggleAll}
            disabled={disabled || knownSheets.length === 0}
          />
          Select all recognized
        </label>
      </header>

      <ul className="sheet-list">
        {sheets.map((sheet) => {
          const isSelected = selected.has(sheet.sheet_name);
          return (
            <li
              key={sheet.sheet_name}
              className={`sheet-item ${!sheet.is_known ? 'sheet-unknown' : ''} ${
                isSelected ? 'selected' : ''
              }`}
            >
              <label>
                <input
                  type="checkbox"
                  checked={isSelected}
                  onChange={() => toggle(sheet.sheet_name)}
                  disabled={disabled || !sheet.is_known}
                />
                <span className="sheet-name">{sheet.sheet_name}</span>
                {sheet.sector_code ? (
                  <span className="sheet-sector">{sheet.sector_code}</span>
                ) : (
                  <span />
                )}
                <span className="sheet-rows">{sheet.data_rows} data rows</span>
                {!sheet.is_known ? (
                  <span
                    className="sheet-warn"
                    title="This sheet is not in the recognized mapping and will be skipped."
                  >
                    Unrecognized
                  </span>
                ) : (
                  <span />
                )}
              </label>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
