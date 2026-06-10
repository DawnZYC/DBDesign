import { useEffect, useRef, useState } from 'react';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
interface ChartSeries {
  key: string;
  label: string;
  color: string;
}

interface ChartSpec {
  chartType: 'line' | 'bar' | 'area';
  title: string;
  xKey: string;
  series: ChartSeries[];
  data: Record<string, unknown>[];
}

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  toolCalls?: ToolCallRecord[];
  charts?: ChartSpec[];
  status?: 'streaming' | 'done' | 'error';
}

interface ToolCallRecord {
  tool: string;
  input?: unknown;
  output?: string;
}

interface SSEChunk {
  type: 'token' | 'tool_start' | 'tool_end' | 'chart' | 'error' | 'done';
  content: string;
}

// ---------------------------------------------------------------------------
// API helper – SSE streaming fetch
// ---------------------------------------------------------------------------
async function* streamChat(
  message: string,
  history: Array<{ role: string; content: string }>,
  signal: AbortSignal,
): AsyncGenerator<SSEChunk> {
  const response = await fetch('/api/agent/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, history }),
    signal,
  });

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }

  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';

    for (const line of lines) {
      if (line.startsWith('data:')) {
        const raw = line.slice(5).trim();
        if (!raw || raw === '[DONE]') continue;
        try {
          yield JSON.parse(raw) as SSEChunk;
        } catch {
          // ignore malformed lines
        }
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Tiny markdown renderer (no external deps)
// ---------------------------------------------------------------------------
function renderMarkdown(text: string): string {
  return text
    // code block
    .replace(/```[\w]*\n([\s\S]*?)```/g, '<pre><code>$1</code></pre>')
    // inline code
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    // bold
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    // italic
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    // headers
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    // unordered list
    .replace(/^\s*[-*] (.+)$/gm, '<li>$1</li>')
    // ordered list items
    .replace(/^\d+\. (.+)$/gm, '<li>$1</li>')
    // paragraphs / line breaks
    .replace(/\n{2,}/g, '</p><p>')
    .replace(/\n/g, '<br/>');
}

// ---------------------------------------------------------------------------
// Suggestion chips
// ---------------------------------------------------------------------------
const SUGGESTIONS = [
  'List all solar technologies',
  'Compare wind power CAPEX trends from 2020 to 2040',
  'Which technologies have the lowest emission factor?',
  'Search for energy storage related technologies',
  'Show all technologies in sector_id = 1',
];

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ChartWidget({ spec }: { spec: ChartSpec }) {
  const { chartType, title, xKey, series, data } = spec;

  const commonProps = {
    data,
    margin: { top: 8, right: 16, left: 0, bottom: 4 },
  };

  const axes = (
    <>
      <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
      <XAxis
        dataKey={xKey}
        tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
        tickLine={false}
        axisLine={{ stroke: 'var(--border)' }}
      />
      <YAxis
        tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
        tickLine={false}
        axisLine={false}
        width={56}
      />
      <Tooltip
        contentStyle={{
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          borderRadius: '6px',
          fontSize: '12px',
        }}
      />
      <Legend wrapperStyle={{ fontSize: '12px', paddingTop: '8px' }} />
    </>
  );

  return (
    <div className="chart-widget">
      {title && <p className="chart-title">{title}</p>}
      <ResponsiveContainer width="100%" height={260}>
        {chartType === 'bar' ? (
          <BarChart {...commonProps}>
            {axes}
            {series.map((s) => (
              <Bar key={s.key} dataKey={s.key} name={s.label} fill={s.color} radius={[3, 3, 0, 0]} />
            ))}
          </BarChart>
        ) : chartType === 'area' ? (
          <AreaChart {...commonProps}>
            {axes}
            {series.map((s) => (
              <Area
                key={s.key}
                type="monotone"
                dataKey={s.key}
                name={s.label}
                stroke={s.color}
                fill={s.color}
                fillOpacity={0.15}
                strokeWidth={2}
                dot={{ r: 3 }}
                activeDot={{ r: 5 }}
              />
            ))}
          </AreaChart>
        ) : (
          <LineChart {...commonProps}>
            {axes}
            {series.map((s) => (
              <Line
                key={s.key}
                type="monotone"
                dataKey={s.key}
                name={s.label}
                stroke={s.color}
                strokeWidth={2}
                dot={{ r: 3 }}
                activeDot={{ r: 5 }}
              />
            ))}
          </LineChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}

function ToolCallBadge({ call }: { call: ToolCallRecord }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="tool-call-badge">
      <button
        type="button"
        className="tool-call-trigger"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="tool-call-icon" aria-hidden>⚙</span>
        <span className="tool-call-name">{call.tool}</span>
        <span className="tool-call-chevron">{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <div className="tool-call-body">
          {call.input !== undefined && (
            <div className="tool-call-section">
              <span className="tool-call-label">Input</span>
              <pre className="tool-call-pre">{JSON.stringify(call.input, null, 2)}</pre>
            </div>
          )}
          {call.output && (
            <div className="tool-call-section">
              <span className="tool-call-label">Output (preview)</span>
              <pre className="tool-call-pre">{call.output}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === 'user';
  return (
    <div className={`chat-message chat-message--${msg.role}`}>
      <div className="chat-avatar" aria-hidden>
        {isUser ? 'U' : 'AI'}
      </div>
      <div className="chat-bubble">
        {(msg.toolCalls ?? []).map((tc, i) => (
          <ToolCallBadge key={i} call={tc} />
        ))}
        {(msg.charts ?? []).map((chart, i) => (
          <ChartWidget key={i} spec={chart} />
        ))}
        <div
          className="chat-text"
          // biome-ignore lint: controlled markdown render
          dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.content) }}
        />
        {msg.status === 'streaming' && <span className="chat-cursor" aria-hidden />}
        {msg.status === 'error' && (
          <span className="chat-error-label">Connection error — please try again</span>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main ChatView
// ---------------------------------------------------------------------------
export function ChatView() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  // Auto-scroll on new content
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [input]);

  const historyForAPI = messages
    .filter((m) => m.status !== 'streaming' && m.role !== 'assistant' || m.status === 'done')
    .map((m) => ({ role: m.role, content: m.content }));

  async function sendMessage(text: string) {
    if (!text.trim() || loading) return;

    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: text.trim(),
      status: 'done',
    };

    const assistantMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'assistant',
      content: '',
      toolCalls: [],
      status: 'streaming',
    };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setInput('');
    setLoading(true);

    const ctrl = new AbortController();
    abortRef.current = ctrl;

    try {
      for await (const chunk of streamChat(text.trim(), historyForAPI, ctrl.signal)) {
        if (chunk.type === 'token') {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsg.id ? { ...m, content: m.content + chunk.content } : m,
            ),
          );
        } else if (chunk.type === 'tool_start') {
          const parsed = JSON.parse(chunk.content);
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsg.id
                ? {
                    ...m,
                    toolCalls: [
                      ...(m.toolCalls ?? []),
                      { tool: parsed.tool, input: parsed.input },
                    ],
                  }
                : m,
            ),
          );
        } else if (chunk.type === 'chart') {
          try {
            const spec = JSON.parse(chunk.content) as ChartSpec;
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMsg.id
                  ? { ...m, charts: [...(m.charts ?? []), spec] }
                  : m,
              ),
            );
          } catch {
            // ignore malformed chart spec
          }
        } else if (chunk.type === 'tool_end') {
          const parsed = JSON.parse(chunk.content);
          setMessages((prev) =>
            prev.map((m) => {
              if (m.id !== assistantMsg.id) return m;
              const calls = [...(m.toolCalls ?? [])];
              // Attach output to last matching tool call
              for (let i = calls.length - 1; i >= 0; i--) {
                if (calls[i].tool === parsed.tool && calls[i].output === undefined) {
                  calls[i] = { ...calls[i], output: parsed.output };
                  break;
                }
              }
              return { ...m, toolCalls: calls };
            }),
          );
        } else if (chunk.type === 'done') {
          setMessages((prev) =>
            prev.map((m) => (m.id === assistantMsg.id ? { ...m, status: 'done' } : m)),
          );
        } else if (chunk.type === 'error') {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsg.id
                ? { ...m, content: m.content || chunk.content, status: 'error' }
                : m,
            ),
          );
        }
      }
    } catch (err: unknown) {
      if ((err as Error).name !== 'AbortError') {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsg.id ? { ...m, status: 'error' } : m,
          ),
        );
      }
    } finally {
      setLoading(false);
      abortRef.current = null;
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  }

  function handleStop() {
    abortRef.current?.abort();
    setMessages((prev) =>
      prev.map((m) => (m.status === 'streaming' ? { ...m, status: 'done' } : m)),
    );
    setLoading(false);
  }

  function handleClear() {
    if (loading) handleStop();
    setMessages([]);
  }

  return (
    <div className="chat-view">
      {/* ---- Message list ---- */}
      <div className="chat-messages" role="log" aria-live="polite">
        {messages.length === 0 && (
          <div className="chat-empty">
            <div className="chat-empty-icon" aria-hidden>◈</div>
            <p className="chat-empty-title">Energy Data AI Assistant</p>
            <p className="chat-empty-desc">
              Built on LangGraph, PostgreSQL, and ChromaDB. Ask questions in natural language,
              compare data across years, and explore technology cost trends.
            </p>
            <div className="chat-suggestions">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  type="button"
                  className="chat-suggestion-chip"
                  onClick={() => sendMessage(s)}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((msg) => (
          <MessageBubble key={msg.id} msg={msg} />
        ))}
        <div ref={bottomRef} />
      </div>

      {/* ---- Input bar ---- */}
      <div className="chat-input-bar">
        {messages.length > 0 && (
          <button
            type="button"
            className="chat-clear-btn"
            onClick={handleClear}
            title="Clear conversation"
            aria-label="Clear conversation"
          >
            ↺
          </button>
        )}
        <div className="chat-input-wrap">
          <textarea
            ref={textareaRef}
            className="chat-input"
            placeholder="Ask a question… Enter to send, Shift+Enter for new line"
            value={input}
            rows={1}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={loading}
            aria-label="Chat input"
          />
          {loading ? (
            <button
              type="button"
              className="chat-send-btn chat-stop-btn"
              onClick={handleStop}
              aria-label="Stop generation"
            >
              ■
            </button>
          ) : (
            <button
              type="button"
              className="chat-send-btn"
              onClick={() => sendMessage(input)}
              disabled={!input.trim()}
              aria-label="Send"
            >
              ↑
            </button>
          )}
        </div>
        <p className="chat-hint">AI responses may contain errors. Verify critical decisions against the source database.</p>
      </div>
    </div>
  );
}
