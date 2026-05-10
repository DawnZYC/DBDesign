import { useEffect, useMemo, useState } from 'react';
import { listGeographies, listSectors, listTechnologies } from '../api';
import type { Geography, Sector, TechnologyListResponse } from '../types';

interface TechnologyListProps {
  onSelect: (technologyId: number) => void;
  selectedId: number | null;
}

const PAGE_SIZE = 20;

export function TechnologyList({ onSelect, selectedId }: TechnologyListProps) {
  const [sectors, setSectors] = useState<Sector[]>([]);
  const [geographies, setGeographies] = useState<Geography[]>([]);
  const [sectorId, setSectorId] = useState<number | ''>('');
  const [geographyId, setGeographyId] = useState<number | ''>('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [data, setData] = useState<TechnologyListResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load dictionaries once.
  useEffect(() => {
    Promise.all([listSectors(), listGeographies()])
      .then(([s, g]) => {
        setSectors(s);
        setGeographies(g);
      })
      .catch((err) => setError((err as Error).message));
  }, []);

  // Refresh the list when any filter changes.
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    listTechnologies({
      sector_id: sectorId === '' ? undefined : sectorId,
      geography_id: geographyId === '' ? undefined : geographyId,
      q: search.trim() || undefined,
      page,
      page_size: PAGE_SIZE,
    })
      .then((res) => {
        if (cancelled) return;
        setData(res);
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setError((err as Error).message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [sectorId, geographyId, search, page]);

  const totalPages = useMemo(() => {
    if (!data) return 1;
    return Math.max(1, Math.ceil(data.total / data.page_size));
  }, [data]);

  const handleFilterChange =
    <T,>(setter: (v: T) => void) =>
    (v: T) => {
      setter(v);
      setPage(1);
    };

  const totalLabel = data
    ? `${data.total.toLocaleString()} ${data.total === 1 ? 'technology' : 'technologies'}`
    : '';

  return (
    <section className="tech-list">
      <header className="panel-head">
        <h3>Technologies</h3>
        <span className="panel-count">{totalLabel}</span>
      </header>

      <div className="tech-list-filters">
        <input
          type="text"
          placeholder="Search by code or description"
          value={search}
          onChange={(e) => handleFilterChange(setSearch)(e.target.value)}
          className="filter-input"
          aria-label="Search technologies"
        />
        <select
          value={sectorId}
          onChange={(e) =>
            handleFilterChange(setSectorId)(e.target.value === '' ? '' : Number(e.target.value))
          }
          aria-label="Filter by sector"
        >
          <option value="">All sectors</option>
          {sectors.map((s) => (
            <option key={s.sector_id} value={s.sector_id}>
              {s.sector_name}
            </option>
          ))}
        </select>
        <select
          value={geographyId}
          onChange={(e) =>
            handleFilterChange(setGeographyId)(e.target.value === '' ? '' : Number(e.target.value))
          }
          aria-label="Filter by geography"
        >
          <option value="">All geographies</option>
          {geographies.map((g) => (
            <option key={g.geography_id} value={g.geography_id}>
              {g.geography_code}
            </option>
          ))}
        </select>
      </div>

      {error && (
        <div className="tech-list-error">
          Unable to load technologies. {error}
        </div>
      )}

      {loading && data === null && <div className="tech-loading">Loading technologies</div>}

      {!loading && data?.items.length === 0 && (
        <div className="tech-empty">No technologies match the current filters.</div>
      )}

      {data && data.items.length > 0 && (
        <ul className="tech-cards">
          {data.items.map((it) => {
            const isSelected = selectedId === it.technology_id;
            const yearRange =
              it.year_min != null && it.year_max != null
                ? `${it.year_min} – ${it.year_max}`
                : '—';
            const lifetime =
              it.technology_lifetime_years != null
                ? `${it.technology_lifetime_years} yr`
                : '—';
            return (
              <li
                key={it.technology_id}
                className={`tech-card ${isSelected ? 'selected' : ''}`}
                onClick={() => onSelect(it.technology_id)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    onSelect(it.technology_id);
                  }
                }}
              >
                <div className="tech-card-top">
                  <span className="tech-card-code" title={it.technology_code}>
                    {it.technology_code}
                  </span>
                  <span className="tech-card-tags">
                    <span className="tag tag-sector">{it.sector_code}</span>
                    <span className="tag tag-geo">{it.geography_code}</span>
                    {it.grade && <span className="tag tag-grade">Grade {it.grade}</span>}
                  </span>
                </div>
                <p className="tech-card-desc" title={it.technology_description ?? ''}>
                  {it.technology_description ?? 'No description provided'}
                </p>
                <div className="tech-card-stats">
                  <span className="tech-card-stat">
                    <span className="tech-card-stat-label">Lifetime</span>
                    <span className="tech-card-stat-value">{lifetime}</span>
                  </span>
                  <span className="tech-card-stat">
                    <span className="tech-card-stat-label">Year range</span>
                    <span className="tech-card-stat-value">{yearRange}</span>
                  </span>
                  <span className="tech-card-stat">
                    <span className="tech-card-stat-label">Records</span>
                    <span className="tech-card-stat-value">{it.year_count}</span>
                  </span>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      <footer className="tech-list-pager">
        <span className="pager-info">
          {data ? `Page ${page} of ${totalPages}` : ''}
          {loading && data !== null ? ' · refreshing' : ''}
        </span>
        <div className="pager-buttons">
          <button
            type="button"
            className="pager-btn"
            disabled={page <= 1 || loading}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            Previous
          </button>
          <span className="pager-page">
            {page} / {totalPages}
          </span>
          <button
            type="button"
            className="pager-btn"
            disabled={page >= totalPages || loading}
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
          >
            Next
          </button>
        </div>
      </footer>
    </section>
  );
}
