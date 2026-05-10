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
        <p>Select a technology from the list to view its details.</p>
      </section>
    );
  }

  if (loading && detail === null) {
    return (
      <section className="tech-detail">
        <div className="loading">Loading technology details</div>
      </section>
    );
  }

  if (error) {
    return (
      <section className="tech-detail">
        <div className="error">Unable to load this technology. {error}</div>
      </section>
    );
  }

  if (!detail) return null;

  const yearRange =
    detail.years.length > 0
      ? `${detail.years[0].data_year} – ${detail.years[detail.years.length - 1].data_year}`
      : '—';

  return (
    <section className="tech-detail">
      <header className="detail-header">
        <div className="detail-header-top">
          <div>
            <h3>{detail.technology_code}</h3>
            <div className="detail-tags">
              <span className="tag tag-sector">{detail.sector_name}</span>
              <span className="tag tag-geo">{detail.geography_code}</span>
              {detail.grade && <span className="tag tag-grade">Grade {detail.grade}</span>}
            </div>
          </div>
        </div>

        {detail.technology_description && (
          <p className="detail-desc">{detail.technology_description}</p>
        )}

        <dl className="detail-meta">
          <div>
            <dt>Start year</dt>
            <dd>{detail.technology_start_year ?? '—'}</dd>
          </div>
          <div>
            <dt>Lifetime</dt>
            <dd>
              {detail.technology_lifetime_years != null
                ? `${detail.technology_lifetime_years} yr`
                : '—'}
            </dd>
          </div>
          <div>
            <dt>Year range</dt>
            <dd>{yearRange}</dd>
          </div>
          <div>
            <dt>Records</dt>
            <dd>{detail.years.length}</dd>
          </div>
        </dl>
      </header>

      <div className="detail-section-head">
        <h4>Yearly data</h4>
        <span className="detail-section-meta">
          {detail.years.length} {detail.years.length === 1 ? 'record' : 'records'}
        </span>
      </div>

      {detail.years.length === 0 ? (
        <div className="empty-rows">No yearly data available for this technology.</div>
      ) : (
        <div className="year-table-wrap">
          <table className="year-table">
            <thead>
              <tr className="group-header">
                <th rowSpan={2} className="year-col">
                  Year
                </th>
                <th colSpan={1}>Emission</th>
                <th colSpan={3} className="group-divider">
                  Costs
                </th>
                <th colSpan={2} className="group-divider">
                  Performance
                </th>
                <th colSpan={2} className="group-divider">
                  Capacity
                </th>
                <th colSpan={1} className="group-divider">
                  Output mix
                </th>
              </tr>
              <tr className="col-header">
                <th>Factor</th>
                <th className="group-divider">CAPEX</th>
                <th>Fixed OPEX</th>
                <th>Var. OPEX</th>
                <th className="group-divider">Efficiency</th>
                <th>Heat rate</th>
                <th className="group-divider">Value</th>
                <th>Bound</th>
                <th className="group-divider">Commodities</th>
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
      <td className="year-cell-year">{year.data_year}</td>
      <td className="num">
        <ValueWithUnit value={year.emission_factor} unit={year.emission_factor_unit} />
      </td>
      <td className="num group-divider">
        <ValueWithUnit value={year.capex} unit={year.capex_unit} />
      </td>
      <td className="num">
        <ValueWithUnit value={year.fixed_opex} unit={year.fixed_opex_unit} />
      </td>
      <td className="num">
        <ValueWithUnit value={year.variable_opex} unit={year.variable_opex_unit} />
      </td>
      <td className="efficiency-cell group-divider">
        {year.efficiency_text ? (
          <div className="year-cell-pair">
            <span>{year.efficiency_text}</span>
            {year.efficiency_unit && <span className="year-cell-unit">{year.efficiency_unit}</span>}
          </div>
        ) : (
          <span className="year-cell-empty">—</span>
        )}
      </td>
      <td className="num">{formatNum(year.heat_rate)}</td>
      <td className="num group-divider">{formatNum(year.capacity_value)}</td>
      <td>
        {year.capacity_bound_type ? (
          <span>{year.capacity_bound_type}</span>
        ) : (
          <span className="year-cell-empty">—</span>
        )}
      </td>
      <td className="group-divider">{renderCommodities(year.commodities)}</td>
    </tr>
  );
}

function ValueWithUnit({ value, unit }: { value: string | null; unit: string | null }) {
  if (value == null) return <span className="year-cell-empty">—</span>;
  return (
    <div className="year-cell-pair">
      <span>{formatNum(value)}</span>
      {unit && <span className="year-cell-unit">{unit}</span>}
    </div>
  );
}

function renderCommodities(rows: CommodityRow[]) {
  if (rows.length === 0) return <span className="year-cell-empty">—</span>;
  return (
    <div className="commodity-list">
      {rows.map((c, idx) => {
        const share = c.share_text ?? (c.share_value != null ? c.share_value : null);
        return (
          <span key={`${c.commodity_code}-${idx}`} className="commodity-chip">
            {c.commodity_code}
            {share && <span className="commodity-share">&nbsp;·&nbsp;{share}</span>}
          </span>
        );
      })}
    </div>
  );
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
