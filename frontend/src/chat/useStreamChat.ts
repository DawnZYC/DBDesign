/**
 * useStreamChat — Chat 状态管理 hook。
 *
 * 职责：
 *  - 维护 messages 列表（ChatMessage[]）
 *  - sendMessage() 触发 SSE 流：
 *      1. append user message
 *      2. append 空 assistant message（status: 'streaming'）
 *      3. 逐事件更新该 assistant message
 *      4. done 时 status → 'done'
 *  - clearMessages() 清空对话
 *  - isStreaming 表示当前是否有未完成的流
 *
 * 设计要点：
 *  - 用 useRef 持有最新 messages，避免 streamChat 回调闭包捕获过期值
 *  - updateLastAssistant 使用 functional update，保证并发安全
 *  - 每次 sendMessage 生成唯一 msgId（crypto.randomUUID），
 *    回调只操作该 id 的消息（支持未来多并发流）
 */
import { useCallback, useRef, useState } from 'react';

import { streamChat } from '../api';
import type { ChatHistoryMessage } from '../api';
import type { ChatMessage, ToolCallEvent, ToolResultEvent } from '../types';

// ---------------------------------------------------------------------------
// 工具函数
// ---------------------------------------------------------------------------
function newId(): string {
  return typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID()
    : Math.random().toString(36).slice(2);
}

/** 不可变更新：把 messages 中 id===targetId 的那条用 updater 处理 */
function updateById(
  msgs: ChatMessage[],
  targetId: string,
  updater: (m: ChatMessage) => ChatMessage,
): ChatMessage[] {
  return msgs.map((m) => (m.id === targetId ? updater(m) : m));
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------
export interface UseStreamChatReturn {
  messages: ChatMessage[];
  sendMessage: (text: string) => void;
  isStreaming: boolean;
  clearMessages: () => void;
}

export function useStreamChat(): UseStreamChatReturn {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);

  // ref 持有最新 messages，供回调读取（不触发重新渲染）
  const messagesRef = useRef<ChatMessage[]>([]);
  messagesRef.current = messages;

  // 当前流的 AbortController（避免同时发两条）
  const ctrlRef = useRef<AbortController | null>(null);

  const sendMessage = useCallback((text: string) => {
    if (!text.trim()) return;

    // 强制终止前一个未完成的流
    ctrlRef.current?.abort();

    // 1. 构造对话历史（user / assistant 交替，去掉无内容的）
    const history: ChatHistoryMessage[] = messagesRef.current
      .filter((m) => m.content.trim())
      .map((m) => ({ role: m.role, content: m.content }));

    // 2. 追加用户消息
    const userMsg: ChatMessage = {
      id: newId(),
      role: 'user',
      content: text,
      status: 'done',
    };

    // 3. 追加空 assistant 消息（占位，streaming 时逐步填充）
    const assistantId = newId();
    const assistantMsg: ChatMessage = {
      id: assistantId,
      role: 'assistant',
      content: '',
      plan: [],
      toolCalls: [],
      toolResults: [],
      chartSpec: undefined,
      status: 'streaming',
    };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setIsStreaming(true);

    // 4. 启动 SSE 流
    const ctrl = streamChat(text, history, {
      onAgentStart: (node) => {
        setMessages((prev) =>
          updateById(prev, assistantId, (m) => ({
            ...m,
            currentNode: node as ChatMessage['currentNode'],
          })),
        );
      },

      onPlan: (steps) => {
        setMessages((prev) => updateById(prev, assistantId, (m) => ({ ...m, plan: steps })));
      },

      onToken: (delta) => {
        setMessages((prev) =>
          updateById(prev, assistantId, (m) => ({
            ...m,
            content: m.content + delta,
          })),
        );
      },

      onToolCall: (tool, args) => {
        const event: ToolCallEvent = { tool, args };
        setMessages((prev) =>
          updateById(prev, assistantId, (m) => ({
            ...m,
            toolCalls: [...(m.toolCalls ?? []), event],
          })),
        );
      },

      onToolResult: (data) => {
        const event: ToolResultEvent = {
          tool: data.tool as string,
          row_count: data.row_count as number | undefined,
          truncated: data.truncated as boolean | undefined,
          metric: data.metric as string | undefined,
          sql_summary: data.sql_summary as string | undefined,
        };
        setMessages((prev) =>
          updateById(prev, assistantId, (m) => ({
            ...m,
            toolResults: [...(m.toolResults ?? []), event],
          })),
        );
      },

      onChart: (spec) => {
        setMessages((prev) => updateById(prev, assistantId, (m) => ({ ...m, chartSpec: spec })));
      },

      onError: (message) => {
        setMessages((prev) =>
          updateById(prev, assistantId, (m) => ({
            ...m,
            errorMessage: message,
            status: 'error',
          })),
        );
      },

      onDone: () => {
        setMessages((prev) =>
          updateById(prev, assistantId, (m) => ({
            ...m,
            status: m.status === 'error' ? 'error' : 'done',
            currentNode: undefined,
          })),
        );
        setIsStreaming(false);
        ctrlRef.current = null;
      },
    });

    ctrlRef.current = ctrl;
  }, []); // 无依赖项：所有状态读取都通过 ref 或 functional update

  const clearMessages = useCallback(() => {
    ctrlRef.current?.abort();
    ctrlRef.current = null;
    setMessages([]);
    setIsStreaming(false);
  }, []);

  return { messages, sendMessage, isStreaming, clearMessages };
}
