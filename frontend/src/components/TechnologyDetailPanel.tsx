import { useEffect, useState } from 'react';
import { getTechnology } from '../api';
import type { CommodityRow, TechnologyDetail, TechnologyYearOut } from '../types';

interface TechnologyDetailPanelProps {
  technologyId: number | null;
}

export function TechnologyDetailPanel({ technologyId }: TechnologyDetailPanelProps) {
  const [detail, setDetail] = useState<TechnologyDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (technologyId == null) {
      setDetail(null);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    getTechnology(technologyId)
      .then((d) => {
        if (!cancelled) setDetail(d);
      })
      .catch((err) => {
        if (!cancelled) setError((err as Error).message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [technologyId]);

  if (technologyId == null) {
    return (
      <section className="tech-detail empty">
        <p>Select a technology from the list to view details</p>
      </section>
    );
  }

  if (loading && detail === null) {
    return (
      <section className="tech-detail">
        <div className="loading">Loading...</div>
      </section>
    );
  }

  if (error) {
    return (
      <section className="tech-detail">
        <div className="error">Failed to load: {error}</div>
      </section>
    );
  }

  if (!detail) return null;

  return (
    <section className="tech-detail">
      <header className="detail-header">
        <h3>{detail.technology_code}</h3>
        <div className="detail-tags">
          <span className="tag tag-sector">{detail.sector_name}</span>
          <span className="tag tag-geo">{detail.geography_code}</span>
          {detail.grade && <span className="tag tag-grade">Grade {detail.grade}</span>}
        </div>
        {detail.technology_description && (
          <p className="detail-desc">{detail.technology_description}</p>
        )}
        <dl className="detail-meta">
          <div>
            <dt>Start Year</dt>
            <dd>{detail.technology_start_year ?? '—'}</dd>
          </div>
          <div>
            <dt>Lifetime</dt>
            <dd>
              {detail.technology_lifetime_years != null
                ? `${detail.technology_lifetime_years} years`
                : '—'}
            </dd>
          </div>
          <div>
            <dt>Year Records</dt>
            <dd>{detail.years.length}</dd>
          </div>
        </dl>
      </header>

      {detail.years.length === 0 ? (
        <div className="empty-rows">This technology has no year data</div>
      ) : (
        <div className="year-table-wrap">
          <table className="year-table">
            <thead>
              <tr>
                <th>Year</th>
                <th className="ralign">EF</th>
                <th>EF unit</th>
                <th className="ralign">CAPEX</th>
                <th>CAPEX unit</th>
                <th className="ralign">Fixed OPEX</th>
                <th className="ralign">Var OPEX</th>
                <th>Efficiency</th>
                <th className="ralign">Capacity</th>
                <th>Bound</th>
                <th>Commodities</th>
              </tr>
            </thead>
            <tbody>
              {detail.years.map((y) => (
                <YearRow key={y.technology_year_id} year={y} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function YearRow({ year }: { year: TechnologyYearOut }) {
  return (
    <tr>
      <td className="num">{year.data_year}</td>
      <td className="ralign num">{formatNum(year.emission_factor)}</td>
      <td>{year.emission_factor_unit ?? ''}</td>
      <td className="ralign num">{formatNum(year.capex)}</td>
      <td>{year.capex_unit ?? ''}</td>
      <td className="ralign num">{formatNum(year.fixed_opex)}</td>
      <td className="ralign num">{formatNum(year.variable_opex)}</td>
      <td className="efficiency-cell">
        {year.efficiency_text ? (
          <>
            <strong>{year.efficiency_text}</strong>
            {year.efficiency_unit && (
              <span className="muted"> · {year.efficiency_unit}</span>
            )}
          </>
        ) : (
          '—'
        )}
      </td>
      <td className="ralign num">{formatNum(year.capacity_value)}</td>
      <td>{year.capacity_bound_type ?? ''}</td>
      <td>{summarizeCommodities(year.commodities)}</td>
    </tr>
  );
}

function summarizeCommodities(rows: CommodityRow[]): string {
  if (rows.length === 0) return '—';
  return rows
    .map((c) => {
      const share = c.share_text ?? (c.share_value != null ? c.share_value : '');
      return share ? `${c.commodity_code}:${share}` : c.commodity_code;
    })
    .join(' + ');
}

function formatNum(value: string | null): string {
  if (value == null) return '—';
  const n = Number(value);
  if (!Number.isFinite(n)) return value;
  if (n === 0) return '0';
  if (Math.abs(n) >= 100) return n.toFixed(2);
  if (Math.abs(n) >= 1) return n.toFixed(3);
  return n.toFixed(4);
}
