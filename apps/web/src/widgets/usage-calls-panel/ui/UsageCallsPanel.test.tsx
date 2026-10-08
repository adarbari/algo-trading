import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest';

import { callAt, callId, emptyUsage, usageFixture } from '@/entities/llm-usage';
import { gql, TestQueryProvider } from '@/shared/api';

import { UsageCallsPanel } from './UsageCallsPanel';

vi.mock('@/shared/api', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  gql: vi.fn(),
}));

function serve(data: unknown) {
  vi.mocked(gql).mockResolvedValue({ llmUsage: data });
}

// jsdom has no layout: give elements a size so the table has a viewport to fill.
beforeAll(() => {
  Object.defineProperty(HTMLElement.prototype, 'offsetHeight', {
    configurable: true,
    get: () => 400,
  });
  Object.defineProperty(HTMLElement.prototype, 'offsetWidth', {
    configurable: true,
    get: () => 1000,
  });
});
afterAll(() => {
  Reflect.deleteProperty(HTMLElement.prototype, 'offsetHeight');
  Reflect.deleteProperty(HTMLElement.prototype, 'offsetWidth');
});

const view = (onSelect = vi.fn()) =>
  render(
    <TestQueryProvider>
      <UsageCallsPanel selected={null} onSelect={onSelect} />
    </TestQueryProvider>,
  );

describe('UsageCallsPanel', () => {
  it('lists the calls with every column, an unreported value as a dash, never zero', async () => {
    serve(usageFixture());
    view();
    const grid = await screen.findByRole('grid', { name: 'Recent text-model calls' });
    expect(grid).toHaveTextContent('2026-10-08 14:00:00 UTC');
    expect(grid).toHaveTextContent('claude_cli');
    expect(grid).toHaveTextContent('Reported (notional)');
    expect(grid).toHaveTextContent('skipped budget');
    expect(grid).not.toHaveTextContent('$0.0000');
  });

  it('chooses a call by its id when a row is activated', async () => {
    serve(usageFixture());
    const onSelect = vi.fn();
    view(onSelect);
    await userEvent.click(await screen.findByText('2026-10-08 13:00:00 UTC'));
    expect(onSelect).toHaveBeenCalledWith(callId(callAt(1)));
  });

  it('says when no call has been recorded', async () => {
    serve(emptyUsage());
    view();
    expect(await screen.findByText('No text-model calls recorded yet')).toBeInTheDocument();
  });
});
