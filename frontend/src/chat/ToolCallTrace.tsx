/**
 * ToolCallTrace — collapsible panel showing the agent's tool calls.
 *
 * Each tool_call is paired with its tool_result:
 *   ▶ run_sql          ← collapsed
 *   ▼ run_sql
 *     ↳ 12 rows · metric=capex   ← expanded
 */
import { useState } from 'react';
import type { ToolCallEvent, ToolResultEvent } from '../types';

interface Props {
  toolCalls: ToolCallEvent[];
  toolResults: ToolResultEvent[];
}

const NODE_LABELS: Record<string, string> = {
  run_sql: 'SQL query',
  lookup_terminology: 'Terminology',
  convert_unit: 'Unit conversion',
  lookup_emission_factor: 'Emission factor',
  forecast_trend: 'Trend forecast',
  recommend_chart: 'Chart suggestion',
};

export function ToolCallTrace({ toolCalls, toolResults }: Props) {
  const [open, setOpen] = useState(false);

  if (toolCalls.length === 0) return null;

  const label = `Tool calls · ${toolCalls.length}`;

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
                {/* call row */}
                <div className="tool-call-row">
                  <span className="tool-call-icon">⚙</span>
                  <span className="tool-call-name">{call.tool}</span>
                  <span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>
                    {NODE_LABELS[call.tool] ?? call.tool}
                  </span>
                </div>

                {/* result row (arrives async, may be missing) */}
                {result && (
                  <div className="tool-result-row">
                    <span className="tool-result-ok">✓</span>
                    <span className="tool-result-meta">
                      {result.row_count != null && `${result.row_count} rows`}
                      {result.truncated && ' (truncated)'}
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
                      {/* auxiliary tools (terminology / unit / emission / forecast) */}
                      {result.row_count == null && result.output_summary && (
                        <span style={{ color: '#9ca3af' }} title={result.output_summary}>
                          {result.output_summary.slice(0, 80)}
                          {result.output_summary.length > 80 ? '…' : ''}
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
