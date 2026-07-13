/**
 * streamChat SSE client tests.
 *
 * fetch is stubbed with hand-built ReadableStream bodies so we can verify the
 * manual SSE parser: event dispatch, sse-starlette CRLF delimiters, events
 * split across network chunks, and the error paths.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { streamChat, type StreamCallbacks } from '../api';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
const encoder = new TextEncoder();

/** Build a Response-like object whose body streams the given text chunks. */
function sseResponse(chunks: string[], init: { ok?: boolean; status?: number } = {}) {
  const { ok = true, status = 200 } = init;
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const c of chunks) controller.enqueue(encoder.encode(c));
      controller.close();
    },
  });
  return { ok, status, body } as unknown as Response;
}

/** sse-starlette 2.x style event block (CRLF field delimiters). */
function sse(event: string, data: unknown): string {
  return `event: ${event}\r\ndata: ${JSON.stringify(data)}\r\n\r\n`;
}

function recordingCallbacks() {
  const events: Array<[string, unknown]> = [];
  const push = (type: string) => (payload: unknown, extra?: unknown) =>
    events.push([type, extra === undefined ? payload : [payload, extra]]);
  const callbacks: StreamCallbacks = {
    onAgentStart: push('agent_start'),
    onPlan: push('plan'),
    onToken: push('token'),
    onToolCall: (tool, args) => events.push(['tool_call', [tool, args]]),
    onToolResult: push('tool_result'),
    onChart: push('chart'),
    onError: push('error'),
    onDone: push('done'),
  };
  return { events, callbacks };
}

/** Wait until the async stream loop drains. */
async function flush() {
  await new Promise((r) => setTimeout(r, 10));
}

let fetchSpy: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchSpy = vi.fn();
  vi.stubGlobal('fetch', fetchSpy);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// Request shape
// ---------------------------------------------------------------------------
describe('streamChat request', () => {
  it('POSTs message/history/language to /api/chat/stream', async () => {
    fetchSpy.mockResolvedValueOnce(sseResponse([sse('done', { trace_id: 't' })]));
    streamChat('hi', [{ role: 'user', content: 'before' }], {}, 'Chinese');
    await flush();

    const [url, init] = fetchSpy.mock.calls[0];
    expect(url).toBe('/api/chat/stream');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({
      message: 'hi',
      history: [{ role: 'user', content: 'before' }],
      language: 'Chinese',
    });
  });

  it('omits the language field when not set', async () => {
    fetchSpy.mockResolvedValueOnce(sseResponse([sse('done', { trace_id: 't' })]));
    streamChat('hi', [], {});
    await flush();
    expect(JSON.parse(fetchSpy.mock.calls[0][1].body).language).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// Event dispatch
// ---------------------------------------------------------------------------
describe('streamChat SSE parsing', () => {
  it('dispatches the full event protocol to the right callbacks', async () => {
    const stream = [
      sse('agent_start', { node: 'planner' }),
      sse('plan', { steps: ['a', 'b'] }),
      sse('tool_call', { tool: 'run_sql', args: { metric: 'capex' } }),
      sse('tool_result', { tool: 'run_sql', row_count: 3 }),
      sse('token', { delta: 'Hel' }),
      sse('token', { delta: 'lo' }),
      sse('chart', { spec: { series: [] } }),
      sse('error', { message: 'partial issue' }),
      sse('done', { trace_id: 'trace-9' }),
    ].join('');
    fetchSpy.mockResolvedValueOnce(sseResponse([stream]));

    const { events, callbacks } = recordingCallbacks();
    streamChat('q', [], callbacks);
    await flush();

    expect(events).toEqual([
      ['agent_start', 'planner'],
      ['plan', ['a', 'b']],
      ['tool_call', ['run_sql', { metric: 'capex' }]],
      ['tool_result', { tool: 'run_sql', row_count: 3 }],
      ['token', 'Hel'],
      ['token', 'lo'],
      ['chart', { series: [] }],
      ['error', 'partial issue'],
      ['done', 'trace-9'],
    ]);
  });

  it('handles an event split across two network chunks', async () => {
    const block = sse('token', { delta: 'split-token' });
    const mid = Math.floor(block.length / 2);
    fetchSpy.mockResolvedValueOnce(
      sseResponse([block.slice(0, mid), block.slice(mid), sse('done', { trace_id: 't' })]),
    );

    const { events, callbacks } = recordingCallbacks();
    streamChat('q', [], callbacks);
    await flush();

    expect(events).toContainEqual(['token', 'split-token']);
  });

  it('parses plain \\n\\n delimited events and ignores comments / non-JSON', async () => {
    const stream =
      ': keep-alive comment\n\n' +
      'event: token\ndata: {"delta":"lf-style"}\n\n' +
      'data: not-json\n\n' +
      'event: done\ndata: {"trace_id":"t"}\n\n';
    fetchSpy.mockResolvedValueOnce(sseResponse([stream]));

    const { events, callbacks } = recordingCallbacks();
    streamChat('q', [], callbacks);
    await flush();

    expect(events).toEqual([
      ['token', 'lf-style'],
      ['done', 't'],
    ]);
  });

  it('flushes a trailing event that lacks the final delimiter', async () => {
    fetchSpy.mockResolvedValueOnce(
      sseResponse(['event: token\r\ndata: {"delta":"tail"}']), // no trailing \r\n\r\n
    );
    const { events, callbacks } = recordingCallbacks();
    streamChat('q', [], callbacks);
    await flush();
    expect(events).toContainEqual(['token', 'tail']);
  });
});

// ---------------------------------------------------------------------------
// Error paths
// ---------------------------------------------------------------------------
describe('streamChat error handling', () => {
  it('reports HTTP errors and still fires onDone', async () => {
    fetchSpy.mockResolvedValueOnce(sseResponse([], { ok: false, status: 503 }));
    const { events, callbacks } = recordingCallbacks();
    streamChat('q', [], callbacks);
    await flush();
    expect(events).toEqual([
      ['error', 'HTTP 503'],
      ['done', ''],
    ]);
  });

  it('reports network failures', async () => {
    fetchSpy.mockRejectedValueOnce(new TypeError('Failed to fetch'));
    const { events, callbacks } = recordingCallbacks();
    streamChat('q', [], callbacks);
    await flush();
    expect(events[0][0]).toBe('error');
    expect(String(events[0][1])).toContain('Failed to fetch');
  });

  it('stays silent on abort', async () => {
    const abortErr = new DOMException('aborted', 'AbortError');
    fetchSpy.mockRejectedValueOnce(abortErr);
    const { events, callbacks } = recordingCallbacks();
    const ctrl = streamChat('q', [], callbacks);
    ctrl.abort();
    await flush();
    expect(events).toEqual([]);
  });
});
