/**
 * ChartBubble — embedded ECharts bubble.
 *
 * Renders the full ECharts option (incl. dataset) pushed by the Visualizer.
 * On data-point click, looks up raw_row_id from dataset.dimensions at runtime
 * (no fixed index assumed) and fires onPointClick to open CellTraceModal.
 */
import ReactECharts from 'echarts-for-react';

interface Props {
  spec: Record<string, unknown>;
  onPointClick: (rawRowId: number) => void;
}

/** Extract raw_row_id from an ECharts click-event param. */
function extractRawRowId(
  params: { data?: unknown; dimensionNames?: string[] },
  dimensions: string[],
): number | null {
  const idx = dimensions.indexOf('raw_row_id');
  if (idx < 0) return null;

  // Dataset mode: params.data is a row array.
  const row = params.data;
  if (Array.isArray(row) && row[idx] != null) {
    const id = Number(row[idx]);
    return Number.isFinite(id) ? id : null;
  }

  // Aggregated mode (no raw_row_id): return null.
  return null;
}

export function ChartBubble({ spec, onPointClick }: Props) {
  const meta = (spec._meta as Record<string, unknown>) ?? {};
  const chartType = (meta.chart_type as string) ?? '';
  const metric = (meta.metric as string) ?? '';
  const unit = (meta.unit as string) ?? '';
  const rowCount = (meta.row_count as number) ?? 0;
  const chartRowCount = (meta.chart_row_count as number) ?? rowCount;
  const truncated = (meta.truncated as boolean) ?? false;

  // Pull dataset.dimensions for the click handler. The dataset may be a
  // dict (single) or a list (multiple, incl. transform/filter) — the first
  // entry is always the raw-data dataset, so dimensions come from it.
  const rawDataset = Array.isArray(spec.dataset)
    ? ((spec.dataset as Record<string, unknown>[])[0] ?? {})
    : ((spec.dataset as Record<string, unknown>) ?? {});
  const dimensions: string[] = (rawDataset.dimensions as string[]) ?? [];

  // Source-cell trace is only possible for raw rows (which carry raw_row_id). Aggregated
  // charts (sum/avg) have no raw_row_id, so don't advertise or wire up clicking.
  const traceable = dimensions.includes('raw_row_id');

  const handleClick = (params: { data?: unknown; dimensionNames?: string[] }) => {
    const id = extractRawRowId(params, dimensions);
    if (id != null) {
      onPointClick(id);
    }
  };

  // Strip our private _meta field so ECharts does not warn about it.
  const { _meta: _omit, ...echartsOption } = spec;

  return (
    <div className="chart-bubble">
      {/* chart title bar */}
      <div className="chart-bubble-header">
        <span>
          <span className="chart-bubble-meta">{chartType}</span>
          {metric && (
            <span style={{ marginLeft: 8, fontSize: '12px' }}>
              {metric}
              {unit ? ` (${unit})` : ''}
              {' · '}
              <span style={{ fontVariantNumeric: 'tabular-nums' }}>{rowCount} rows</span>
            </span>
          )}
        </span>
        {traceable && (
          <span className="chart-bubble-hint">Click a data point to trace its source cell</span>
        )}
      </div>

      {/* ECharts chart */}
      <div className="chart-bubble-body">
        <ReactECharts
          option={echartsOption}
          style={{ height: '280px' }}
          onEvents={traceable ? { click: handleClick } : {}}
          notMerge
          lazyUpdate
        />
      </div>

      {/* truncation warning — rowCount is the number of rows the query RETURNED (itself capped
          by the SQL limit), not the database total, so don't imply a known grand total. */}
      {truncated && (
        <div className="chart-truncation-warn">
          ⚠ Charting the first {chartRowCount} of {rowCount} returned rows — narrow the query
          (sector / year range) to plot the full set.
        </div>
      )}
    </div>
  );
}
