/**
 * Chat presentation components: MessageBubble, ToolCallTrace, MessageList.
 *
 * ChartBubble (ECharts canvas) is exercised indirectly and mocked here —
 * jsdom has no canvas, and the chart drawing itself belongs to echarts.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { MessageBubble } from '../chat/MessageBubble';
import { MessageList } from '../chat/MessageList';
import { ToolCallTrace } from '../chat/ToolCallTrace';
import type { ChatMessage } from '../types';

vi.mock('../chat/ChartBubble', () => ({
  ChartBubble: ({ spec }: { spec: Record<string, unknown> }) => (
    <div data-testid="chart-bubble">{JSON.stringify(spec._meta ?? {})}</div>
  ),
}));

const noop = () => {};

function msg(overrides: Partial<ChatMessage>): ChatMessage {
  return { id: 'm1', role: 'assistant', content: '', ...overrides };
}

// ---------------------------------------------------------------------------
// MessageBubble
// ---------------------------------------------------------------------------
describe('MessageBubble', () => {
  it('renders a plain right-side bubble for user messages', () => {
    render(
      <MessageBubble message={msg({ role: 'user', content: 'hi there' })} onPointClick={noop} />,
    );
    expect(screen.getByText('hi there')).toBeInTheDocument();
    expect(screen.getByText('Me')).toBeInTheDocument();
    expect(screen.queryByText('Plan')).not.toBeInTheDocument();
  });

  it('shows the active-node badge while streaming', () => {
    render(
      <MessageBubble
        message={msg({ status: 'streaming', currentNode: 'sql_gen' })}
        onPointClick={noop}
      />,
    );
    expect(screen.getByText('Building query')).toBeInTheDocument();
  });

  it('hides the node badge once the message is done', () => {
    render(
      <MessageBubble
        message={msg({ status: 'done', currentNode: 'sql_gen', content: 'x' })}
        onPointClick={noop}
      />,
    );
    expect(screen.queryByText('Building query')).not.toBeInTheDocument();
  });

  it('renders numbered plan steps', () => {
    render(
      <MessageBubble message={msg({ plan: ['Query capex', 'Draw chart'] })} onPointClick={noop} />,
    );
    expect(screen.getByText('Plan')).toBeInTheDocument();
    expect(screen.getByText('Query capex')).toBeInTheDocument();
    expect(screen.getByText('2.')).toBeInTheDocument();
  });

  it('renders markdown content with bold text', () => {
    render(
      <MessageBubble
        message={msg({ content: 'Capex is **rising** fast', status: 'done' })}
        onPointClick={noop}
      />,
    );
    const strong = screen.getByText('rising');
    expect(strong.tagName).toBe('STRONG');
  });

  it('renders the chart bubble when a spec is present', () => {
    render(
      <MessageBubble
        message={msg({ chartSpec: { _meta: { chart_type: 'line' } } })}
        onPointClick={noop}
      />,
    );
    expect(screen.getByTestId('chart-bubble')).toHaveTextContent('line');
  });

  it('renders the error notice', () => {
    render(
      <MessageBubble
        message={msg({ status: 'error', errorMessage: 'LLM not configured' })}
        onPointClick={noop}
      />,
    );
    expect(screen.getByText(/LLM not configured/)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// ToolCallTrace
// ---------------------------------------------------------------------------
describe('ToolCallTrace', () => {
  it('renders nothing without tool calls', () => {
    const { container } = render(<ToolCallTrace toolCalls={[]} toolResults={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('is collapsed by default and expands on click', () => {
    render(
      <ToolCallTrace
        toolCalls={[{ tool: 'run_sql', args: {} }]}
        toolResults={[{ tool: 'run_sql', row_count: 12, truncated: true, metric: 'capex' }]}
      />,
    );
    expect(screen.getByText('Tool calls · 1')).toBeInTheDocument();
    expect(screen.queryByText('run_sql')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button'));

    expect(screen.getByText('run_sql')).toBeInTheDocument();
    expect(screen.getByText(/12 rows/)).toBeInTheDocument();
    expect(screen.getByText(/truncated/)).toBeInTheDocument();
    expect(screen.getByText(/capex/)).toBeInTheDocument();
  });

  it('shows the output summary for auxiliary tools', () => {
    render(
      <ToolCallTrace
        toolCalls={[{ tool: 'convert_unit', args: {} }]}
        toolResults={[{ tool: 'convert_unit', output_summary: '{"value": 23.88}' }]}
      />,
    );
    fireEvent.click(screen.getByRole('button'));
    expect(screen.getByText(/23.88/)).toBeInTheDocument();
    expect(screen.getByText('Unit conversion')).toBeInTheDocument();
  });

  it('renders a call row even when its result has not arrived yet', () => {
    render(<ToolCallTrace toolCalls={[{ tool: 'forecast_trend', args: {} }]} toolResults={[]} />);
    fireEvent.click(screen.getByRole('button'));
    expect(screen.getByText('forecast_trend')).toBeInTheDocument();
    expect(screen.queryByText('✓')).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// MessageList
// ---------------------------------------------------------------------------
describe('MessageList', () => {
  it('renders every message as a bubble', () => {
    const messages: ChatMessage[] = [
      msg({ id: 'u1', role: 'user', content: 'question' }),
      msg({ id: 'a1', content: 'answer', status: 'done' }),
    ];
    render(<MessageList messages={messages} onPointClick={noop} />);
    expect(screen.getByText('question')).toBeInTheDocument();
    expect(screen.getByText('answer')).toBeInTheDocument();
  });

  it('renders an empty container without messages', () => {
    const { container } = render(<MessageList messages={[]} onPointClick={noop} />);
    expect(container.querySelector('.message-list')).toBeInTheDocument();
  });
});
