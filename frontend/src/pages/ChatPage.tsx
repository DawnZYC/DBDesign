/**
 * ChatPage — AI assistant main page (M4).
 *
 * Layout:
 *   chat-header (title + actions) / message-list (scrollable) /
 *   chat-input-area (textarea + send). CellTraceModal overlays on top.
 *
 * Keyboard: Enter sends, Shift+Enter inserts a newline.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

import { CellTraceModal } from '../components/CellTraceModal';
import { KnowledgePanel } from '../components/KnowledgePanel';
import { MessageList } from '../chat/MessageList';
import { useStreamChat } from '../chat/useStreamChat';
import { checkHealth } from '../api';
import '../chat/chat.css';

// Example prompts shown on the empty state — one per intent path (data / tool / concept).
const EXAMPLE_PROMPTS = [
  'Power sector capex trend 2018–2050',
  'What is BIOMASS01, and which technologies use it?',
  'Convert 1 PJ of natural gas to ktoe',
];

// Reply-language options. `value` is the language name the model understands ('' = auto,
// i.e. match the question's language); `label` is shown to the user.
const LANGUAGES: Array<{ value: string; label: string }> = [
  { value: '', label: 'Auto' },
  { value: 'English', label: 'English' },
  { value: 'Chinese', label: '中文' },
  { value: 'Spanish', label: 'Español' },
  { value: 'French', label: 'Français' },
  { value: 'German', label: 'Deutsch' },
  { value: 'Japanese', label: '日本語' },
];

export function ChatPage() {
  const { messages, sendMessage, isStreaming, stop, clearMessages } = useStreamChat();
  const [inputText, setInputText] = useState('');
  const [cellTraceId, setCellTraceId] = useState<number | null>(null);
  const [showKnowledge, setShowKnowledge] = useState(false);
  const [llmReady, setLlmReady] = useState(true);
  const [language, setLanguage] = useState(''); // '' = auto
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Pre-flight: warn if the LLM provider has no API key, instead of failing per-message.
  useEffect(() => {
    checkHealth()
      .then((h) => setLlmReady(h.llm ? h.llm.configured : true))
      .catch(() => setLlmReady(true)); // a failed health check is surfaced elsewhere
  }, []);

  /* ---- Send logic ---- */
  const handleSend = useCallback(() => {
    const text = inputText.trim();
    if (!text || isStreaming) return;
    setInputText('');
    sendMessage(text, language);
    // Return focus to the input after sending.
    setTimeout(() => textareaRef.current?.focus(), 0);
  }, [inputText, isStreaming, sendMessage, language]);

  /* ---- Enter sends / Shift+Enter newline ---- */
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  /* ---- Auto-grow textarea ---- */
  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const el = e.target;
    setInputText(el.value);
    // Reset height, then expand to scrollHeight.
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 140)}px`;
  };

  return (
    <div className="chat-page">
      {/* Header */}
      <div className="chat-header">
        <span className="chat-header-title">
          ✦ AI Assistant
          {isStreaming && (
            <span style={{ fontSize: 11, color: 'var(--primary)', fontWeight: 400 }}>
              · thinking…
            </span>
          )}
        </span>
        <span className="chat-header-actions">
          <label className="chat-lang">
            <span className="chat-lang-label">Language</span>
            <select
              className="chat-lang-select"
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              title="Language the assistant replies in"
              aria-label="Reply language"
            >
              {LANGUAGES.map((l) => (
                <option key={l.value} value={l.value}>
                  {l.label}
                </option>
              ))}
            </select>
          </label>{' '}
          <button type="button" className="chat-clear-btn" onClick={() => setShowKnowledge(true)}>
            Knowledge
          </button>{' '}
          <button
            type="button"
            className="chat-clear-btn"
            onClick={clearMessages}
            disabled={messages.length === 0}
          >
            Clear chat
          </button>
        </span>
      </div>

      {showKnowledge && <KnowledgePanel onClose={() => setShowKnowledge(false)} />}

      {!llmReady && (
        <div className="chat-llm-warning">
          ⚠ No LLM API key is configured on the server — the assistant can't answer yet. Set the
          provider's API key in <code>backend/.env</code> and restart.
        </div>
      )}

      {/* Empty state: a short welcome + clickable example prompts. */}
      {messages.length === 0 ? (
        <div className="chat-empty">
          <div className="chat-empty-title">Ask about the energy-system model</div>
          <div className="chat-empty-sub">
            Query data, look up a code, or convert units — in plain language.
          </div>
          <div className="chat-empty-examples">
            {EXAMPLE_PROMPTS.map((p) => (
              <button
                key={p}
                type="button"
                className="chat-example-chip"
                onClick={() => !isStreaming && sendMessage(p, language)}
                disabled={isStreaming}
              >
                {p}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <MessageList messages={messages} onPointClick={setCellTraceId} />
      )}

      {/* Input area */}
      <div className="chat-input-area">
        <textarea
          ref={textareaRef}
          className="chat-textarea"
          placeholder={
            isStreaming
              ? 'The assistant is responding…'
              : 'Ask a question, e.g. "Power sector capex trend 2018-2050" (Enter to send)'
          }
          value={inputText}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          disabled={isStreaming}
          rows={1}
        />
        {isStreaming ? (
          <button
            type="button"
            className="chat-send-btn chat-stop-btn"
            onClick={stop}
            title="Stop generating"
          >
            ◼ Stop
          </button>
        ) : (
          <button
            type="button"
            className="chat-send-btn"
            onClick={handleSend}
            disabled={!inputText.trim()}
          >
            Send
          </button>
        )}
      </div>

      {/* Source-cell trace overlay */}
      {cellTraceId !== null && (
        <CellTraceModal rawRowId={cellTraceId} onClose={() => setCellTraceId(null)} />
      )}
    </div>
  );
}
