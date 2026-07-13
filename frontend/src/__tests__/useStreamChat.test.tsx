/**
 * useStreamChat hook tests.
 *
 * The api.streamChat call is mocked: each test captures the callback set the
 * hook passes in, then drives those callbacks manually to simulate SSE events
 * and asserts how the hook's message state evolves.
 */
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ChatHistoryMessage, StreamCallbacks } from '../api';
import { useStreamChat } from '../chat/useStreamChat';

// ---------------------------------------------------------------------------
// api.streamChat mock
// ---------------------------------------------------------------------------
const streamChatMock = vi.hoisted(() => vi.fn());
vi.mock('../api', async (importOriginal) => {
  const mod = await importOriginal<typeof import('../api')>();
  return { ...mod, streamChat: streamChatMock };
});

let captured: {
  message: string;
  history: ChatHistoryMessage[];
  callbacks: StreamCallbacks;
  language?: string;
  ctrl: AbortController;
}[];

beforeEach(() => {
  captured = [];
  streamChatMock.mockImplementation(
    (
      message: string,
      history: ChatHistoryMessage[],
      callbacks: StreamCallbacks,
      language?: string,
    ) => {
      const ctrl = new AbortController();
      captured.push({ message, history, callbacks, language, ctrl });
      return ctrl;
    },
  );
});

afterEach(() => {
  vi.clearAllMocks();
});

const last = () => captured[captured.length - 1];

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
describe('useStreamChat', () => {
  it('appends a user message and a streaming assistant placeholder', () => {
    const { result } = renderHook(() => useStreamChat());

    act(() => result.current.sendMessage('capex 2030'));

    expect(result.current.isStreaming).toBe(true);
    expect(result.current.messages).toHaveLength(2);
    const [user, assistant] = result.current.messages;
    expect(user).toMatchObject({ role: 'user', content: 'capex 2030', status: 'done' });
    expect(assistant).toMatchObject({ role: 'assistant', content: '', status: 'streaming' });
  });

  it('ignores blank input', () => {
    const { result } = renderHook(() => useStreamChat());
    act(() => result.current.sendMessage('   '));
    expect(result.current.messages).toHaveLength(0);
    expect(streamChatMock).not.toHaveBeenCalled();
  });

  it('accumulates streamed tokens into the assistant message', () => {
    const { result } = renderHook(() => useStreamChat());
    act(() => result.current.sendMessage('q'));

    act(() => {
      last().callbacks.onToken?.('Capex ');
      last().callbacks.onToken?.('rises.');
    });

    expect(result.current.messages[1].content).toBe('Capex rises.');
  });

  it('records plan, node, tool calls/results and the chart spec', () => {
    const { result } = renderHook(() => useStreamChat());
    act(() => result.current.sendMessage('q'));

    act(() => {
      last().callbacks.onAgentStart?.('planner');
      last().callbacks.onPlan?.(['step 1', 'step 2']);
      last().callbacks.onToolCall?.('run_sql', { metric: 'capex' });
      last().callbacks.onToolResult?.({ tool: 'run_sql', row_count: 5, truncated: false });
      last().callbacks.onChart?.({ series: [{ type: 'line' }] });
    });

    const assistant = result.current.messages[1];
    expect(assistant.currentNode).toBe('planner');
    expect(assistant.plan).toEqual(['step 1', 'step 2']);
    expect(assistant.toolCalls).toEqual([{ tool: 'run_sql', args: { metric: 'capex' } }]);
    expect(assistant.toolResults?.[0]).toMatchObject({ tool: 'run_sql', row_count: 5 });
    expect(assistant.chartSpec).toEqual({ series: [{ type: 'line' }] });
  });

  it('finalizes the message on done', () => {
    const { result } = renderHook(() => useStreamChat());
    act(() => result.current.sendMessage('q'));

    act(() => {
      last().callbacks.onToken?.('answer');
      last().callbacks.onDone?.('trace-1');
    });

    expect(result.current.isStreaming).toBe(false);
    expect(result.current.messages[1]).toMatchObject({
      status: 'done',
      content: 'answer',
      currentNode: undefined,
    });
  });

  it('marks the message as error and keeps that state through done', () => {
    const { result } = renderHook(() => useStreamChat());
    act(() => result.current.sendMessage('q'));

    act(() => {
      last().callbacks.onError?.('LLM not configured');
      last().callbacks.onDone?.('');
    });

    expect(result.current.messages[1]).toMatchObject({
      status: 'error',
      errorMessage: 'LLM not configured',
    });
  });

  it('sends prior non-empty turns as history, with the language passthrough', () => {
    const { result } = renderHook(() => useStreamChat());

    act(() => result.current.sendMessage('first'));
    act(() => {
      last().callbacks.onToken?.('reply one');
      last().callbacks.onDone?.('t1');
    });
    act(() => result.current.sendMessage('second', 'Chinese'));

    expect(captured).toHaveLength(2);
    expect(last().language).toBe('Chinese');
    expect(last().history).toEqual([
      { role: 'user', content: 'first' },
      { role: 'assistant', content: 'reply one' },
    ]);
  });

  it('stop() aborts the stream and un-spins the assistant message', () => {
    const { result } = renderHook(() => useStreamChat());
    act(() => result.current.sendMessage('q'));

    const ctrl = last().ctrl;
    act(() => {
      last().callbacks.onToken?.('partial');
      result.current.stop();
    });

    expect(ctrl.signal.aborted).toBe(true);
    expect(result.current.isStreaming).toBe(false);
    expect(result.current.messages[1]).toMatchObject({ status: 'done', content: 'partial' });
  });

  it('stop() is a no-op when nothing is streaming', () => {
    const { result } = renderHook(() => useStreamChat());
    act(() => result.current.stop());
    expect(result.current.isStreaming).toBe(false);
  });

  it('clearMessages aborts and resets everything', () => {
    const { result } = renderHook(() => useStreamChat());
    act(() => result.current.sendMessage('q'));
    const ctrl = last().ctrl;

    act(() => result.current.clearMessages());

    expect(ctrl.signal.aborted).toBe(true);
    expect(result.current.messages).toEqual([]);
    expect(result.current.isStreaming).toBe(false);
  });

  it('a new send aborts the previous in-flight stream', () => {
    const { result } = renderHook(() => useStreamChat());
    act(() => result.current.sendMessage('one'));
    const first = last().ctrl;
    act(() => result.current.sendMessage('two'));

    expect(first.signal.aborted).toBe(true);
    expect(result.current.messages).toHaveLength(4);
  });
});
