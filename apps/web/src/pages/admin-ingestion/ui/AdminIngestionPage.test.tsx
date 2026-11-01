import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AdminIngestionPage } from './AdminIngestionPage';

const { stub } = vi.hoisted(() => ({ stub: (name: string) => () => `[${name}]` }));
vi.mock('@/widgets/ingestion-summary', () => ({ IngestionSummary: stub('summary') }));
vi.mock('@/widgets/completeness-panel', () => ({
  CompletenessPanel: ({ selected }: { selected: { dataset: string } | null }) =>
    `[grid ${selected?.dataset ?? 'none'}]`,
}));
vi.mock('@/widgets/known-coverage-panel', () => ({ KnownCoveragePanel: stub('known') }));
vi.mock('@/widgets/chain-coverage-panel', () => ({ ChainCoveragePanel: stub('chains') }));
vi.mock('@/widgets/drilldown-panel', () => ({ DrilldownPanel: stub('drilldown') }));
vi.mock('@/widgets/quality-checks-panel', () => ({ QualityChecksPanel: stub('quality') }));
vi.mock('@/widgets/verification-panel', () => ({ VerificationPanel: stub('verification') }));
vi.mock('@/widgets/review-items-panel', () => ({ ReviewItemsPanel: stub('review') }));
vi.mock('@/widgets/recent-runs-panel', () => ({ RecentRunsPanel: stub('runs') }));

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('AdminIngestionPage', () => {
  it('shows the tonight view first and each other view on its tab', async () => {
    render(<AdminIngestionPage onSelectCell={vi.fn()} onClearCell={vi.fn()} />);
    expect(screen.getByRole('heading', { level: 1, name: 'Nightly run' })).toBeInTheDocument();
    for (const name of ['summary', 'runs', 'quality', 'chains']) {
      expect(document.body).toHaveTextContent(`[${name}]`);
    }
    expect(document.body).not.toHaveTextContent('[verification]');
    await userEvent.click(screen.getByRole('tab', { name: 'Checks against IBKR' }));
    expect(document.body).toHaveTextContent('[verification]');
    await userEvent.click(screen.getByRole('tab', { name: 'Review items' }));
    expect(document.body).toHaveTextContent('[review]');
  });

  it('opens the coverage view with the selected cell', () => {
    render(
      <AdminIngestionPage
        selected={{ dataset: 'bars/1d', session: '2026-10-02' }}
        onSelectCell={vi.fn()}
        onClearCell={vi.fn()}
      />,
    );
    for (const name of ['grid bars/1d', 'drilldown', 'known']) {
      expect(document.body).toHaveTextContent(`[${name}]`);
    }
  });

  it('on a phone the drill-down opens in a sheet only once a cell is chosen, and closing clears it', async () => {
    vi.stubGlobal('innerWidth', 375);
    const onClearCell = vi.fn();
    const props = { onSelectCell: vi.fn(), onClearCell };
    const { rerender } = render(<AdminIngestionPage {...props} />);
    expect(screen.queryByText('[drilldown]')).not.toBeInTheDocument();
    rerender(
      <AdminIngestionPage selected={{ dataset: 'bars/1d', session: '2026-10-02' }} {...props} />,
    );
    expect(await screen.findByText('[drilldown]')).toBeInTheDocument();
    await userEvent.keyboard('{Escape}');
    expect(onClearCell).toHaveBeenCalled();
  });
});
