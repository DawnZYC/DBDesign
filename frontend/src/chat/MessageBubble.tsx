/**
 * MessageBubble — 单条消息气泡。
 *
 * 用户消息：简单文本，右对齐蓝色气泡。
 * AI 消息：从上到下依次显示：
 *   1. 当前节点徽章（streaming 中）
 *   2. Planner 步骤列表（有 plan 时）
 *   3. 工具调用 Trace（可折叠）
 *   4. Markdown 正文（流式打字机）
 *   5. ECharts 图表气泡
 *   6. 错误提示（如有）
 */
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

import type { ChatMessage } from '../types';
import { ChartBubble } from './ChartBubble';
import { ToolCallTrace } from './ToolCallTrace';

const NODE_DISPLAY: Record<string, string> = {
  planner: '规划中',
  sql_gen: '生成查询',
  interpreter: '解读数据',
  visualizer: '生成图表',
};

interface Props {
  message: ChatMessage;
  onPointClick: (rawRowId: number) => void;
}

export function MessageBubble({ message, onPointClick }: Props) {
  /* ---- 用户气泡 ---- */
  if (message.role === 'user') {
    return (
      <div className="message-row user">
        <div className="avatar avatar-user">我</div>
        <div className="bubble user-bubble">{message.content}</div>
      </div>
    );
  }

  /* ---- AI 气泡 ---- */
  const isStreaming = message.status === 'streaming';

  return (
    <div className="message-row assistant">
      <div className="avatar avatar-ai">AI</div>

      <div className={`bubble assistant-bubble ${isStreaming ? 'streaming' : ''}`}>
        {/* 1. 当前节点徽章（streaming 时显示） */}
        {isStreaming && message.currentNode && (
          <div className="node-badge">
            <span className="node-badge-dot" />
            {NODE_DISPLAY[message.currentNode] ?? message.currentNode}
          </div>
        )}

        {/* 2. Planner 步骤列表 */}
        {message.plan && message.plan.length > 0 && (
          <div className="plan-list">
            <div className="plan-list-title">执行计划</div>
            {message.plan.map((step, i) => (
              <div key={i} className="plan-step">
                <span className="plan-step-num">{i + 1}.</span>
                <span>{step}</span>
              </div>
            ))}
          </div>
        )}

        {/* 3. 工具调用 Trace */}
        <ToolCallTrace
          toolCalls={message.toolCalls ?? []}
          toolResults={message.toolResults ?? []}
        />

        {/* 4. Markdown 正文（流式） */}
        {message.content && (
          <div className={`markdown-text ${isStreaming ? 'streaming-cursor' : ''}`}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {message.content}
            </ReactMarkdown>
          </div>
        )}

        {/* 5. ECharts 图表气泡 */}
        {message.chartSpec && (
          <ChartBubble spec={message.chartSpec} onPointClick={onPointClick} />
        )}

        {/* 6. 错误提示 */}
        {message.errorMessage && (
          <div className="bubble-error">⚠ {message.errorMessage}</div>
        )}
      </div>
    </div>
  );
}
