/**
 * ChartBubble — 内嵌 ECharts 图表气泡。
 *
 * 接收 Visualizer 推送的完整 ECharts option（包含 dataset），
 * 用 echarts-for-react 渲染；用户点击数据点时从 dataset 取出
 * raw_row_id 并触发 onPointClick 回调（打开 CellTraceModal）。
 *
 * raw_row_id 位于 dataset.dimensions 中，index 由运行时查找决定，
 * 不依赖固定位置（兼容 Visualizer 未来调整 dimension 顺序）。
 */
import ReactECharts from 'echarts-for-react';

interface Props {
  spec: Record<string, unknown>;
  onPointClick: (rawRowId: number) => void;
}

/** 从 ECharts 点击事件参数中提取 raw_row_id。 */
function extractRawRowId(
  params: { data?: unknown; dimensionNames?: string[] },
  dimensions: string[],
): number | null {
  const idx = dimensions.indexOf('raw_row_id');
  if (idx < 0) return null;

  // dataset 模式：params.data 是行数组
  const row = params.data;
  if (Array.isArray(row) && row[idx] != null) {
    const id = Number(row[idx]);
    return Number.isFinite(id) ? id : null;
  }

  // 聚合模式（无 raw_row_id）：返回 null
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

  // 取出 dataset.dimensions 供 click handler 用。
  // 注意 dataset 现在可能是 dict（单 dataset）或 list（多 dataset，含 transform：filter）。
  // 第一份永远是原始数据 dataset，dimensions 都从它取。
  const rawDataset = Array.isArray(spec.dataset)
    ? ((spec.dataset as Record<string, unknown>[])[0] ?? {})
    : ((spec.dataset as Record<string, unknown>) ?? {});
  const dimensions: string[] = (rawDataset.dimensions as string[]) ?? [];

  const handleClick = (params: { data?: unknown; dimensionNames?: string[] }) => {
    const id = extractRawRowId(params, dimensions);
    if (id != null) {
      onPointClick(id);
    }
  };

  // 把 spec 里的 _meta（我们加的私有字段）剔除，避免 ECharts 报警
  const { _meta: _omit, ...echartsOption } = spec;

  return (
    <div className="chart-bubble">
      {/* 图表标题栏 */}
      <div className="chart-bubble-header">
        <span>
          <span className="chart-bubble-meta">{chartType}</span>
          {metric && (
            <span style={{ marginLeft: 8, fontSize: '12px' }}>
              {metric}
              {unit ? ` (${unit})` : ''}
              {' · '}
              <span style={{ fontVariantNumeric: 'tabular-nums' }}>{rowCount} 行</span>
            </span>
          )}
        </span>
        <span className="chart-bubble-hint">点击数据点可查看源单元格</span>
      </div>

      {/* ECharts 图表 */}
      <div className="chart-bubble-body">
        <ReactECharts
          option={echartsOption}
          style={{ height: '280px' }}
          onEvents={{ click: handleClick }}
          notMerge
          lazyUpdate
        />
      </div>

      {/* 截断警告 */}
      {truncated && (
        <div className="chart-truncation-warn">
          ⚠ 数据已截断（图表显示前 {chartRowCount} 行，共 {rowCount} 行），完整结果请调整查询条件
        </div>
      )}
    </div>
  );
}
