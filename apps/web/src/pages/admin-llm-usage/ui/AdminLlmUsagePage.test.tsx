import { render, screen, waitFor } from '@testing-library/react';
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

vi.mock('@/widgets/feature-request-list', () => ({ FeatureRequestList: stub('requests') }));
vi.mock('@/widgets/accepted-formula-list', () => ({ AcceptedFormulaList: stub('formulas') }));

describe('AdminLlmUsagePage', () => {
  it('shows the overview first, the calls with the chosen call and the requests on their tabs', async () => {
    render(<AdminLlmUsagePage onSelectCall={vi.fn()} onClearCall={vi.fn()} />);
    expect(screen.getByRole('heading', { level: 1, name: 'AI and requests' })).toBeInTheDocument();
    for (const name of ['budget', 'trend', 'breakdown', 'reliability']) {
      expect(document.body).toHaveTextContent(`[${name}]`);
    }
    expect(document.body).not.toHaveTextContent('[calls');
    await userEvent.click(screen.getByRole('tab', { name: 'Requests' }));
    await waitFor(() => {
      expect(document.body).toHaveTextContent('[requests]');
    });
    expect(document.body).toHaveTextContent('[formulas]');
  });

  it('opens the calls view for a chosen call and passes it down', async () => {
    render(<AdminLlmUsagePage selected="c1" onSelectCall={vi.fn()} onClearCall={vi.fn()} />);
    await waitFor(() => {
      expect(document.body).toHaveTextContent('[calls c1]');
    });
    expect(document.body).toHaveTextContent('[detail]');
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
