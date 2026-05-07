import { useEffect, useMemo, useState } from 'react';
import { listGeographies, listSectors, listTechnologies } from '../api';
import type {
  Geography,
  Sector,
  TechnologyListItem,
  TechnologyListResponse,
} from '../types';

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

  // 字典只取一次
  useEffect(() => {
    Promise.all([listSectors(), listGeographies()])
      .then(([s, g]) => {
        setSectors(s);
        setGeographies(g);
      })
      .catch((err) => setError((err as Error).message));
  }, []);

  // 列表查询：依赖任何过滤变化
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

  const handleFilterChange = <T,>(setter: (v: T) => void) => (v: T) => {
    setter(v);
    setPage(1);
  };

  return (
    <section className="tech-list">
      <header className="tech-list-filters">
        <input
          type="text"
          placeholder="搜技术 code 或描述…"
          value={search}
          onChange={(e) => handleFilterChange(setSearch)(e.target.value)}
          className="filter-input"
        />
        <select
          value={sectorId}
          onChange={(e) =>
            handleFilterChange(setSectorId)(
              e.target.value === '' ? '' : Number(e.target.value),
            )
          }
        >
          <option value="">全部行业</option>
          {sectors.map((s) => (
            <option key={s.sector_id} value={s.sector_id}>
              {s.sector_name}
            </option>
          ))}
        </select>
        <select
          value={geographyId}
          onChange={(e) =>
            handleFilterChange(setGeographyId)(
              e.target.value === '' ? '' : Number(e.target.value),
            )
          }
        >
          <option value="">全部地区</option>
          {geographies.map((g) => (
            <option key={g.geography_id} value={g.geography_id}>
              {g.geography_code}
            </option>
          ))}
        </select>
      </header>

      {error && (
        <div className="tech-list-error">
          <strong>加载失败：</strong>
          {error}
        </div>
      )}

      <div className="tech-list-table-wrap">
        <table className="tech-table">
          <thead>
            <tr>
              <th>技术代码</th>
              <th>行业</th>
              <th>地区</th>
              <th>描述</th>
              <th className="ralign">寿命</th>
              <th className="ralign">年份范围</th>
              <th className="ralign">条数</th>
            </tr>
          </thead>
          <tbody>
            {loading && data === null && (
              <tr>
                <td colSpan={7} className="tech-table-loading">
                  加载中…
                </td>
              </tr>
            )}
            {data?.items.length === 0 && (
              <tr>
                <td colSpan={7} className="tech-table-empty">
                  没有匹配的技术
                </td>
              </tr>
            )}
            {data?.items.map((it) => (
              <tr
                key={it.technology_id}
                className={selectedId === it.technology_id ? 'selected' : ''}
                onClick={() => onSelect(it.technology_id)}
              >
                <td className="tech-code">{it.technology_code}</td>
                <td>{it.sector_name}</td>
                <td>{it.geography_code}</td>
                <td className="tech-desc" title={it.technology_description ?? ''}>
                  {it.technology_description ?? '—'}
                </td>
                <td className="ralign">
                  {it.technology_lifetime_years ?? '—'}
                  {it.technology_lifetime_years != null && ' yr'}
                </td>
                <td className="ralign">
                  {it.year_min != null && it.year_max != null
                    ? `${it.year_min}–${it.year_max}`
                    : '—'}
                </td>
                <td className="ralign">{it.year_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <footer className="tech-list-pager">
        <span className="pager-info">
          {data ? `共 ${data.total} 条` : '—'}
          {loading && data !== null && ' · 加载中…'}
        </span>
        <div className="pager-buttons">
          <button
            type="button"
            className="btn-secondary pager-btn"
            disabled={page <= 1 || loading}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            上一页
          </button>
          <span className="pager-page">
            {page} / {totalPages}
          </span>
          <button
            type="button"
            className="btn-secondary pager-btn"
            disabled={page >= totalPages || loading}
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
          >
            下一页
          </button>
        </div>
      </footer>
    </section>
  );
}
