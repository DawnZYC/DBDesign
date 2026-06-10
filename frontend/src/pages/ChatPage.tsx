/**
 * ChatPage — AI 助手主页面（M4）。
 *
 * 布局：
 *   ┌─ chat-header ─────────────────┐
 *   │  "AI 助手"        [清空对话]   │
 *   ├─ message-list ────────────────┤
 *   │  (可滚动消息区域)              │
 *   ├─ chat-input-area ─────────────┤
 *   │  [textarea]         [发送]    │
 *   └───────────────────────────────┘
 *   (CellTraceModal 以 portal 形式覆盖在最上层)
 *
 * 键盘快捷键：
 *   - Enter（非 Shift）发送消息
 *   - Shift+Enter 换行
 */
import { useCallback, useRef, useState } from 'react';

import { CellTraceModal } from '../components/CellTraceModal';
import { MessageList } from '../chat/MessageList';
import { useStreamChat } from '../chat/useStreamChat';
import '../chat/chat.css';

export function ChatPage() {
  const { messages, sendMessage, isStreaming, clearMessages } = useStreamChat();
  const [inputText, setInputText] = useState('');
  const [cellTraceId, setCellTraceId] = useState<number | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  /* ---- 发送逻辑 ---- */
  const handleSend = useCallback(() => {
    const text = inputText.trim();
    if (!text || isStreaming) return;
    setInputText('');
    sendMessage(text);
    // 发送后把焦点还给输入框
    setTimeout(() => textareaRef.current?.focus(), 0);
  }, [inputText, isStreaming, sendMessage]);

  /* ---- Enter 发送 / Shift+Enter 换行 ---- */
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  /* ---- 自动撑高 textarea ---- */
  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const el = e.target;
    setInputText(el.value);
    // 重置高度后用 scrollHeight 撑开，实现自动扩展
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 140)}px`;
  };

  return (
    <div className="chat-page">
      {/* 标题栏 */}
      <div className="chat-header">
        <span className="chat-header-title">
          ✦ AI 助手
          {isStreaming && (
            <span style={{ fontSize: 11, color: 'var(--primary)', fontWeight: 400 }}>
              · 思考中…
            </span>
          )}
        </span>
        <button
          type="button"
          className="chat-clear-btn"
          onClick={clearMessages}
          disabled={messages.length === 0}
        >
          清空对话
        </button>
      </div>

      {/* 消息列表 */}
      <MessageList messages={messages} onPointClick={setCellTraceId} />

      {/* 输入区域 */}
      <div className="chat-input-area">
        <textarea
          ref={textareaRef}
          className="chat-textarea"
          placeholder={
            isStreaming
              ? 'AI 正在回复，请稍候…'
              : '输入问题，例如：Power 部门 2030 年的 capex 趋势（Enter 发送，Shift+Enter 换行）'
          }
          value={inputText}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          disabled={isStreaming}
          rows={1}
        />
        <button
          type="button"
          className="chat-send-btn"
          onClick={handleSend}
          disabled={isStreaming || !inputText.trim()}
        >
          {isStreaming ? '…' : '发送'}
        </button>
      </div>

      {/* 源单元格反查浮层 */}
      {cellTraceId !== null && (
        <CellTraceModal rawRowId={cellTraceId} onClose={() => setCellTraceId(null)} />
      )}
    </div>
  );
}
