/**
 * useStreamChat — chat state management hook.
 *
 * Responsibilities:
 *  - own the messages list (ChatMessage[])
 *  - sendMessage() drives the SSE stream:
 *      1. append user message
 *      2. append an empty assistant message (status: 'streaming')
 *      3. update that assistant message event by event
 *      4. on done, status -> 'done'
 *  - clearMessages() resets the conversation
 *  - isStreaming reflects whether a stream is in flight
 *
 * Design notes:
 *  - a ref holds the latest messages so stream callbacks never see stale state
 *  - updateLastAssistant uses functional updates for concurrency safety
 *  - each sendMessage creates a unique msgId (crypto.randomUUID);
 *    callbacks only touch that message (future-proof for concurrent streams)
 */
import { useCallback, useRef, useState } from 'react';

import { streamChat } from '../api';
import type { ChatHistoryMessage } from '../api';
import type { ChatMessage, ToolCallEvent, ToolResultEvent } from '../types';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function newId(): string {
  return typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID()
    : Math.random().toString(36).slice(2);
}

/** Immutable update of the message whose id === targetId. */
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
  sendMessage: (text: string, language?: string) => void;
  isStreaming: boolean;
  stop: () => void;
  clearMessages: () => void;
}

export function useStreamChat(): UseStreamChatReturn {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);

  // Ref mirrors the latest messages for callbacks (no re-render).
  const messagesRef = useRef<ChatMessage[]>([]);
  messagesRef.current = messages;

  // AbortController of the current stream (prevents concurrent sends).
  const ctrlRef = useRef<AbortController | null>(null);

  const sendMessage = useCallback((text: string, language?: string) => {
    if (!text.trim()) return;

    // Abort any unfinished previous stream.
    ctrlRef.current?.abort();

    // 1. Build the history (user/assistant turns, dropping empty ones).
    const history: ChatHistoryMessage[] = messagesRef.current
      .filter((m) => m.content.trim())
      .map((m) => ({ role: m.role, content: m.content }));

    // 2. Append the user message.
    const userMsg: ChatMessage = {
      id: newId(),
      role: 'user',
      content: text,
      status: 'done',
    };

    // 3. Append an empty assistant placeholder to fill while streaming.
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

    // 4. Start the SSE stream.
    const ctrl = streamChat(
      text,
      history,
      {
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
            output_summary: data.output_summary as string | undefined,
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
      },
      language,
    );

    ctrlRef.current = ctrl;
  }, []); // No deps: all state reads go through refs or functional updates.

  // Stop the in-flight stream but keep the partial answer. streamChat ignores the
  // AbortError (no onDone fires), so we finalize the state here ourselves.
  const stop = useCallback(() => {
    if (!ctrlRef.current) return;
    ctrlRef.current.abort();
    ctrlRef.current = null;
    setIsStreaming(false);
    // Mark any still-streaming assistant message as done so it doesn't spin forever.
    setMessages((prev) =>
      prev.map((m) =>
        m.role === 'assistant' && m.status === 'streaming'
          ? { ...m, status: 'done', currentNode: undefined }
          : m,
      ),
    );
  }, []);

  const clearMessages = useCallback(() => {
    ctrlRef.current?.abort();
    ctrlRef.current = null;
    setMessages([]);
    setIsStreaming(false);
  }, []);

  return { messages, sendMessage, isStreaming, stop, clearMessages };
}
