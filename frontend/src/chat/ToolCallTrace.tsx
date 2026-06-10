/**
 * ToolCallTrace — 折叠面板，显示 Agent 工具调用过程。
 *
 * 每条 tool_call 和对应的 tool_result 成对显示：
 *   ▶ run_sql          ← 展开前
 *   ▼ run_sql
 *     ↳ 返回 12 行 · metric=capex  ← 展开后
 */
import { useState } from 'react';
import type { ToolCallEvent, ToolResultEvent } from '../types';

interface Props {
  toolCalls: ToolCallEvent[];
  toolResults: ToolResultEvent[];
}

const NODE_LABELS: Record<string, string> = {
  run_sql: 'SQL 查询',
  lookup_terminology: '术语查询',
  convert_unit: '单位换算',
  lookup_emission_factor: '排放因子',
  forecast_trend: '趋势预测',
  recommend_chart: '图表推荐',
};

export function ToolCallTrace({ toolCalls, toolResults }: Props) {
  const [open, setOpen] = useState(false);

  if (toolCalls.length === 0) return null;

  const label = `工具调用 · ${toolCalls.length} 次`;

  return (
    <div className="tool-trace">
      <button
        type="button"
        className="tool-trace-toggle"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className={`tool-trace-toggle-icon ${open ? 'open' : ''}`}>▶</span>
        {label}
      </button>

      {open && (
        <div className="tool-trace-body">
          {toolCalls.map((call, i) => {
            const result = toolResults[i];
            return (
              <div key={i}>
                {/* 调用行 */}
                <div className="tool-call-row">
                  <span className="tool-call-icon">⚙</span>
                  <span className="tool-call-name">{call.tool}</span>
                  <span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>
                    {NODE_LABELS[call.tool] ?? call.tool}
                  </span>
                </div>

                {/* 返回行（异步到达，可能还没有） */}
                {result && (
                  <div className="tool-result-row">
                    <span className="tool-result-ok">✓</span>
                    <span className="tool-result-meta">
                      {result.row_count != null && `${result.row_count} 行`}
                      {result.truncated && ' (截断)'}
                      {result.metric && ` · ${result.metric}`}
                      {result.sql_summary && (
                        <span
                          style={{ color: '#9ca3af', marginLeft: 6 }}
                          title={result.sql_summary}
                        >
                          {result.sql_summary.slice(0, 60)}
                          {result.sql_summary.length > 60 ? '…' : ''}
                        </span>
                      )}
                    </span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
