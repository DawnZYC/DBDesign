/**
 * MessageBubble — a single chat message.
 *
 * User: plain right-aligned bubble. Assistant, top to bottom:
 * active-node badge (while streaming), planner steps, tool-call trace,
 * streamed Markdown body, ECharts bubble, and error notice (if any).
 */
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

import type { ChatMessage } from '../types';
import { ChartBubble } from './ChartBubble';
import { ToolCallTrace } from './ToolCallTrace';

const NODE_DISPLAY: Record<string, string> = {
  planner: 'Planning',
  sql_gen: 'Building query',
  tool_agent: 'Using tools',
  interpreter: 'Interpreting',
  visualizer: 'Charting',
};

interface Props {
  message: ChatMessage;
  onPointClick: (rawRowId: number) => void;
}

export function MessageBubble({ message, onPointClick }: Props) {
  /* ---- User bubble ---- */
  if (message.role === 'user') {
    return (
      <div className="message-row user">
        <div className="avatar avatar-user">Me</div>
        <div className="bubble user-bubble">{message.content}</div>
      </div>
    );
  }

  /* ---- Assistant bubble ---- */
  const isStreaming = message.status === 'streaming';

  return (
    <div className="message-row assistant">
      <div className="avatar avatar-ai">AI</div>

      <div className={`bubble assistant-bubble ${isStreaming ? 'streaming' : ''}`}>
        {/* 1. Active node badge (while streaming) */}
        {isStreaming && message.currentNode && (
          <div className="node-badge">
            <span className="node-badge-dot" />
            {NODE_DISPLAY[message.currentNode] ?? message.currentNode}
          </div>
        )}

        {/* 2. Planner steps */}
        {message.plan && message.plan.length > 0 && (
          <div className="plan-list">
            <div className="plan-list-title">Plan</div>
            {message.plan.map((step, i) => (
              <div key={i} className="plan-step">
                <span className="plan-step-num">{i + 1}.</span>
                <span>{step}</span>
              </div>
            ))}
          </div>
        )}

        {/* 3. Tool-call trace */}
        <ToolCallTrace
          toolCalls={message.toolCalls ?? []}
          toolResults={message.toolResults ?? []}
        />

        {/* 4. Streamed Markdown body */}
        {message.content && (
          <div className={`markdown-text ${isStreaming ? 'streaming-cursor' : ''}`}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
          </div>
        )}

        {/* 5. ECharts bubble */}
        {message.chartSpec && <ChartBubble spec={message.chartSpec} onPointClick={onPointClick} />}

        {/* 6. Error notice */}
        {message.errorMessage && <div className="bubble-error">⚠ {message.errorMessage}</div>}
      </div>
    </div>
  );
}
