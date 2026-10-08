import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AdminLlmUsagePage } from './AdminLlmUsagePage';

const { stub } = vi.hoisted(() => ({ stub: (name: string) => () => `[${name}]` }));
vi.mock('@/widgets/usage-budget-panel', () => ({ UsageBudgetPanel: stub('budget') }));
vi.mock('@/widgets/usage-trend-panel', () => ({ UsageTrendPanel: stub('trend') }));
vi.mock('@/widgets/usage-breakdown-panel', () => ({ UsageBreakdownPanel: stub('breakdown') }));
vi.mock('@/widgets/usage-reliability-panel', () => ({
  UsageReliabilityPanel: stub('reliability'),
}));
vi.mock('@/widgets/usage-calls-panel', () => ({
  UsageCallsPanel: ({ selected }: { selected: string | null }) => `[calls ${selected ?? 'none'}]`,
}));
vi.mock('@/widgets/usage-call-detail', () => ({ UsageCallDetail: stub('detail') }));

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('AdminLlmUsagePage', () => {
  it('lays out every section and passes the chosen call down', () => {
    render(<AdminLlmUsagePage selected="c1" onSelectCall={vi.fn()} onClearCall={vi.fn()} />);
    expect(screen.getByRole('heading', { level: 1, name: 'LLM usage & cost' })).toBeInTheDocument();
    for (const name of ['budget', 'trend', 'breakdown', 'reliability', 'calls c1', 'detail']) {
      expect(document.body).toHaveTextContent(`[${name}]`);
    }
  });

  it('on a phone the call detail opens in a sheet only once a call is chosen, and closing clears it', async () => {
    vi.stubGlobal('innerWidth', 375);
    const onClearCall = vi.fn();
    const props = { onSelectCall: vi.fn(), onClearCall };
    const { rerender } = render(<AdminLlmUsagePage {...props} />);
    expect(screen.queryByText('[detail]')).not.toBeInTheDocument();
    rerender(<AdminLlmUsagePage selected="c1" {...props} />);
    expect(await screen.findByText('[detail]')).toBeInTheDocument();
    await userEvent.keyboard('{Escape}');
    expect(onClearCall).toHaveBeenCalled();
  });
});
