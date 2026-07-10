import { useEffect, useMemo, useRef, useState } from 'react';
import type { ColumnOverrides, SheetColumnMapping, StandardFieldInfo } from '../types';

/**
 * M5 column-alignment review (pre-import).
 *
 * When a sheet's headers differ from the canonical template (ESM version
 * drift), the Schema-Mapping Agent suggests a target per column with a
 * confidence: auto (>=0.9, applied but editable), review (0.6-0.9, needs
 * confirmation), unmatched (<0.6, skipped unless manually assigned).
 * Confirmed choices are emitted as columnOverrides ({sheet: {src: canonical}}).
 */
interface ColumnMappingReviewProps {
  mappings: SheetColumnMapping[]; // only sheets with layout_is_standard=false
  standardFields: StandardFieldInfo[];
  onChange: (overrides: ColumnOverrides) => void;
  /** Reports whether any field is mapped from more than one column (an ambiguous mapping). */
  onConflictsChange?: (hasConflicts: boolean) => void;
}

const NONE = '__none__'; // dropdown placeholder for "do not import"

function buildInitialChoice(mappings: SheetColumnMapping[]): Record<string, string> {
  const init: Record<string, string> = {};
  for (const m of mappings) {
    for (const s of m.suggestions) {
      const key = `${m.sheet_name}::${s.excel_column}`;
      // auto/review prefill the suggestion; unmatched defaults to skip.
      init[key] = s.status !== 'unmatched' && s.target_column ? s.target_column : NONE;
    }
  }
  return init;
}

export function ColumnMappingReview({
  mappings,
  standardFields,
  onChange,
  onConflictsChange,
}: ColumnMappingReviewProps) {
  // Selected canonical column per (sheet, excel_column); NONE = skip.
  const [choice, setChoice] = useState<Record<string, string>>(() => buildInitialChoice(mappings));

  // Stable content key of the incoming mappings (NOT the array reference). The parent rebuilds
  // the mappings array on every render, so we key effects off this string to (a) avoid an
  // infinite render loop and (b) detect a genuinely new file/preview.
  const mappingsKey = mappings.map((m) => `${m.sheet_name}:${m.suggestions.length}`).join('|');

  // Re-initialize the selections when a different set of sheets arrives (a new file).
  const didMount = useRef(false);
  useEffect(() => {
    if (!didMount.current) {
      didMount.current = true;
      return;
    }
    setChoice(buildInitialChoice(mappings));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mappingsKey]);

  // Per-sheet conflicting targets: a canonical column chosen by more than one source column.
  // We surface these instead of silently dropping one — an ambiguous mapping must be resolved.
  const conflictsBySheet = useMemo(() => {
    const out: Record<string, Set<string>> = {};
    for (const m of mappings) {
      const counts: Record<string, number> = {};
      for (const s of m.suggestions) {
        const t = choice[`${m.sheet_name}::${s.excel_column}`];
        if (t && t !== NONE) counts[t] = (counts[t] ?? 0) + 1;
      }
      out[m.sheet_name] = new Set(Object.keys(counts).filter((t) => counts[t] > 1));
    }
    return out;
  }, [mappings, choice]);

  // Fold choices into overrides and emit upward, whenever the USER changes a selection.
  // Deps are [choice] only (a stable primitive map) — NOT mappings/conflictsBySheet, whose
  // identity changes every parent render and would otherwise cause an infinite update loop.
  // Conflicted (ambiguous) targets are excluded entirely — we never guess which column wins.
  useEffect(() => {
    const overrides: ColumnOverrides = {};
    let conflictCount = 0;
    for (const m of mappings) {
      const counts: Record<string, number> = {};
      for (const s of m.suggestions) {
        const t = choice[`${m.sheet_name}::${s.excel_column}`];
        if (t && t !== NONE) counts[t] = (counts[t] ?? 0) + 1;
      }
      const conflicts = new Set(Object.keys(counts).filter((t) => counts[t] > 1));
      conflictCount += conflicts.size;
      const sheetMap: Record<string, string> = {};
      for (const s of m.suggestions) {
        const target = choice[`${m.sheet_name}::${s.excel_column}`];
        if (target && target !== NONE && !conflicts.has(target)) {
          sheetMap[s.excel_column] = target;
        }
      }
      if (Object.keys(sheetMap).length > 0) overrides[m.sheet_name] = sheetMap;
    }
    onChange(overrides);
    onConflictsChange?.(conflictCount > 0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [choice]);

  if (mappings.length === 0) return null;

  const totalReview = mappings.reduce((n, m) => n + m.review_count, 0);
  const totalConflicts = Object.values(conflictsBySheet).reduce((n, s) => n + s.size, 0);

  return (
    <section className="column-mapping-review">
      <header className="cmr-header">
        <strong>Column alignment review</strong>
        <span className="cmr-hint">
          {mappings.length} sheet(s) differ from the canonical template
          {totalReview > 0 ? `; ${totalReview} column(s) have low confidence, please confirm` : ''}.
          The Schema-Mapping Agent has suggested targets — adjust per column as needed.
        </span>
        {totalConflicts > 0 && (
          <span className="cmr-conflict-banner">
            ⚠ {totalConflicts} field(s) are mapped from more than one column. Conflicted mappings
            are not applied until you make each target unique.
          </span>
        )}
      </header>

      {mappings.map((m) => (
        <div key={m.sheet_name} className="cmr-sheet">
          <div className="cmr-sheet-title">
            {m.sheet_name}
            <span className="cmr-badge cmr-auto">{m.auto_count} auto</span>
            {m.review_count > 0 && (
              <span className="cmr-badge cmr-review">{m.review_count} to confirm</span>
            )}
            {m.unmatched_count > 0 && (
              <span className="cmr-badge cmr-unmatched">{m.unmatched_count} unmatched</span>
            )}
          </div>

          <table className="cmr-table">
            <thead>
              <tr>
                <th>Source</th>
                <th>Header text</th>
                <th>Map to standard field</th>
                <th>Confidence</th>
              </tr>
            </thead>
            <tbody>
              {m.suggestions.map((s) => {
                const key = `${m.sheet_name}::${s.excel_column}`;
                const selected = choice[key] ?? NONE;
                const isConflict =
                  selected !== NONE && (conflictsBySheet[m.sheet_name]?.has(selected) ?? false);
                return (
                  <tr
                    key={key}
                    className={`cmr-row cmr-${s.status}${isConflict ? ' cmr-conflict' : ''}`}
                  >
                    <td className="cmr-col">{s.excel_column}</td>
                    <td className="cmr-srchdr" title={s.reasoning}>
                      {s.excel_header || <em>(empty)</em>}
                    </td>
                    <td>
                      <select
                        className={isConflict ? 'cmr-select-conflict' : undefined}
                        value={selected}
                        onChange={(e) => setChoice((prev) => ({ ...prev, [key]: e.target.value }))}
                      >
                        <option value={NONE}>— do not import —</option>
                        {standardFields.map((f) => (
                          <option key={f.column} value={f.column}>
                            {f.column} · {f.label} ({f.field})
                          </option>
                        ))}
                      </select>
                      {isConflict && <span className="cmr-conflict-tag">duplicate target</span>}
                    </td>
                    <td className="cmr-conf">
                      {s.target_field ? `${Math.round(s.confidence * 100)}%` : '—'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ))}
    </section>
  );
}
