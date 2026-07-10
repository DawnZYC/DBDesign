import { useEffect, useState } from 'react';
import { getTechnology, upsertEmissionFactor } from '../api';
import type { TechnologyDetail } from '../types';
import { TechnologyList } from './TechnologyList';

/**
 * Emission-factor manual entry. Pick a technology on the left, then edit the
 * emission factor (and unit) for each of its years on the right — or add a new
 * year. Writes go through PUT /api/technologies/{id}/emission-factors.
 */
export function EmissionFactorView() {
  const [selectedId, setSelectedId] = useState<number | null>(null);

  return (
    <div className="browse-view">
      <TechnologyList onSelect={setSelectedId} selectedId={selectedId} />
      <EmissionFactorPanel technologyId={selectedId} />
    </div>
  );
}

interface RowState {
  data_year: number;
  value: string; // editable EF, '' means cleared/null
  unit: string;
  baseValue: string; // last-saved value, to detect dirty
  baseUnit: string;
  saving: boolean;
  saved: boolean;
  error: string | null;
}

const DEFAULT_UNIT = 'kt-CO2/PJ';

function toRow(data_year: number, ef: string | null, unit: string | null): RowState {
  const value = ef ?? '';
  const u = unit ?? '';
  return {
    data_year,
    value,
    unit: u,
    baseValue: value,
    baseUnit: u,
    saving: false,
    saved: false,
    error: null,
  };
}

function EmissionFactorPanel({ technologyId }: { technologyId: number | null }) {
  const [detail, setDetail] = useState<TechnologyDetail | null>(null);
  const [rows, setRows] = useState<RowState[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Add-new-year form.
  const [newYear, setNewYear] = useState('');
  const [newValue, setNewValue] = useState('');
  const [newUnit, setNewUnit] = useState(DEFAULT_UNIT);
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  useEffect(() => {
    if (technologyId == null) {
      setDetail(null);
      setRows([]);
      setLoadError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    getTechnology(technologyId)
      .then((d) => {
        if (cancelled) return;
        setDetail(d);
        setRows(
          [...d.years]
            .sort((a, b) => a.data_year - b.data_year)
            .map((y) => toRow(y.data_year, y.emission_factor, y.emission_factor_unit)),
        );
      })
      .catch((err) => {
        if (cancelled) return;
        setLoadError((err as Error).message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [technologyId]);

  const patchRow = (year: number, patch: Partial<RowState>) =>
    setRows((prev) => prev.map((r) => (r.data_year === year ? { ...r, ...patch } : r)));

  function parseValue(raw: string): { ok: true; value: number | null } | { ok: false; msg: string } {
    const trimmed = raw.trim();
    if (trimmed === '') return { ok: true, value: null };
    const n = Number(trimmed);
    if (!Number.isFinite(n)) return { ok: false, msg: 'Enter a number (or leave blank to clear).' };
    return { ok: true, value: n };
  }

  async function saveRow(row: RowState) {
    if (technologyId == null) return;
    const parsed = parseValue(row.value);
    if (!parsed.ok) {
      patchRow(row.data_year, { error: parsed.msg, saved: false });
      return;
    }
    patchRow(row.data_year, { saving: true, error: null, saved: false });
    try {
      const res = await upsertEmissionFactor(technologyId, {
        data_year: row.data_year,
        emission_factor: parsed.value,
        emission_factor_unit: row.unit.trim() || null,
      });
      patchRow(row.data_year, {
        saving: false,
        saved: true,
        error: null,
        value: res.emission_factor ?? '',
        unit: res.emission_factor_unit ?? '',
        baseValue: res.emission_factor ?? '',
        baseUnit: res.emission_factor_unit ?? '',
      });
    } catch (err) {
      patchRow(row.data_year, { saving: false, error: (err as Error).message, saved: false });
    }
  }

  async function addYear() {
    if (technologyId == null) return;
    setAddError(null);
    const yr = Number(newYear.trim());
    if (!Number.isInteger(yr) || yr < 1900 || yr > 2200) {
      setAddError('Enter a valid year (1900–2200).');
      return;
    }
    if (rows.some((r) => r.data_year === yr)) {
      setAddError(`Year ${yr} already exists — edit it in the table above.`);
      return;
    }
    const parsed = parseValue(newValue);
    if (!parsed.ok) {
      setAddError(parsed.msg);
      return;
    }
    setAdding(true);
    try {
      await upsertEmissionFactor(technologyId, {
        data_year: yr,
        emission_factor: parsed.value,
        emission_factor_unit: newUnit.trim() || null,
      });
      // Insert the new row in year order, mark it saved.
      setRows((prev) =>
        [...prev, { ...toRow(yr, parsed.value == null ? null : String(parsed.value), newUnit.trim() || null), saved: true }].sort(
          (a, b) => a.data_year - b.data_year,
        ),
      );
      setNewYear('');
      setNewValue('');
      setNewUnit(DEFAULT_UNIT);
    } catch (err) {
      setAddError((err as Error).message);
    } finally {
      setAdding(false);
    }
  }

  if (technologyId == null) {
    return (
      <section className="tech-detail ef-panel">
        <div className="tech-empty">Select a technology to edit its emission factors.</div>
      </section>
    );
  }

  return (
    <section className="tech-detail ef-panel">
      <header className="panel-head">
        <h3>Emission Factors</h3>
        {detail && <span className="panel-count">{detail.technology_code}</span>}
      </header>

      {loading && <div className="tech-loading">Loading…</div>}
      {loadError && <div className="tech-list-error">Unable to load technology. {loadError}</div>}

      {detail && !loading && (
        <div className="ef-body">
          <p className="ef-hint">
            {detail.technology_description ?? 'No description'} · {detail.sector_name} ·{' '}
            {detail.geography_code}
          </p>

          <table className="ef-table">
            <thead>
              <tr>
                <th>Year</th>
                <th>Emission factor</th>
                <th>Unit</th>
                <th aria-label="actions" />
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && (
                <tr>
                  <td colSpan={4} className="ef-empty-cell">
                    No years yet. Add one below.
                  </td>
                </tr>
              )}
              {rows.map((row) => {
                const dirty = row.value !== row.baseValue || row.unit !== row.baseUnit;
                return (
                  <tr key={row.data_year}>
                    <td className="ef-year">{row.data_year}</td>
                    <td>
                      <input
                        type="text"
                        inputMode="decimal"
                        className="ef-input"
                        value={row.value}
                        placeholder="(none)"
                        onChange={(e) =>
                          patchRow(row.data_year, { value: e.target.value, saved: false, error: null })
                        }
                        aria-label={`Emission factor for ${row.data_year}`}
                      />
                    </td>
                    <td>
                      <input
                        type="text"
                        className="ef-input ef-unit"
                        value={row.unit}
                        placeholder={DEFAULT_UNIT}
                        onChange={(e) =>
                          patchRow(row.data_year, { unit: e.target.value, saved: false, error: null })
                        }
                        aria-label={`Unit for ${row.data_year}`}
                      />
                    </td>
                    <td className="ef-action">
                      <button
                        type="button"
                        className="ef-save-btn"
                        disabled={!dirty || row.saving}
                        onClick={() => saveRow(row)}
                      >
                        {row.saving ? 'Saving…' : 'Save'}
                      </button>
                      {row.saved && !dirty && <span className="ef-saved">Saved</span>}
                      {row.error && <span className="ef-row-error">{row.error}</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          <div className="ef-add">
            <h4>Add a year</h4>
            <div className="ef-add-row">
              <input
                type="text"
                inputMode="numeric"
                className="ef-input ef-add-year"
                placeholder="Year"
                value={newYear}
                onChange={(e) => setNewYear(e.target.value)}
                aria-label="New year"
              />
              <input
                type="text"
                inputMode="decimal"
                className="ef-input"
                placeholder="Emission factor"
                value={newValue}
                onChange={(e) => setNewValue(e.target.value)}
                aria-label="New emission factor"
              />
              <input
                type="text"
                className="ef-input ef-unit"
                placeholder="Unit"
                value={newUnit}
                onChange={(e) => setNewUnit(e.target.value)}
                aria-label="New unit"
              />
              <button type="button" className="ef-add-btn" disabled={adding} onClick={addYear}>
                {adding ? 'Adding…' : 'Add'}
              </button>
            </div>
            {addError && <div className="ef-row-error ef-add-error">{addError}</div>}
          </div>
        </div>
      )}
    </section>
  );
}
