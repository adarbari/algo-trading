import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { toIdeasData, type IdeasData, type IdeasResponse } from '@/entities/idea';
import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { TopIdeas } from './TopIdeas';

const hooks = vi.hoisted(() => ({ useIdeas: vi.fn() }));
vi.mock('@/entities/idea', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useIdeas: hooks.useIdeas,
}));

const pick = (config_id: string, decision: string, score: number) => ({
  config_id,
  config_version: 1,
  user: 'abhinav',
  session: '2026-10-02',
  decision,
  score,
  reasons: '',
  criteria: [],
  columns: {},
  criterion_values: {},
  flags: [],
});

const response: IdeasResponse = {
  session: '2026-10-02',
  priority: ['vrp', 'liq'],
  total: 3,
  screeners: [
    { config_id: 'vrp', user: 'abhinav', name: 'VRP scanner', version: 1 },
    { config_id: 'liq', user: 'abhinav', name: 'Liquidity', version: 1 },
  ],
  items: [
    {
      rank: 1,
      instrument_id: 'EQ:A',
      symbol: 'AAPL',
      picks: [
        {
          ...pick('vrp', 'QUALIFIED', 84),
          columns: { iv30: 0.31, hv30: 0.21, iv_hv_ratio: 1.49, put_roc: 0.019 },
        },
        pick('liq', 'QUALIFIED', 91),
      ],
      next_earnings_date: '2026-10-29',
      days_to_earnings: 27,
      closest_expiry_dte: 36,
      earnings_before_expiry: true,
    },
    {
      rank: 2,
      instrument_id: 'EQ:K',
      symbol: 'KO',
      picks: [{ ...pick('liq', 'WATCH', 66), flags: ['leveraged_inverse'] }],
      next_earnings_date: '2026-10-08',
      days_to_earnings: 6,
      closest_expiry_dte: 8,
      earnings_before_expiry: false,
    },
    {
      rank: 3,
      instrument_id: 'EQ:S',
      symbol: 'SPY',
      picks: [pick('liq', 'QUALIFIED', 88)],
      next_earnings_date: null,
      days_to_earnings: null,
      closest_expiry_dte: null,
      earnings_before_expiry: null,
    },
  ],
};
const data = toIdeasData(response);

function setup() {
  const handlers = {
    onCompare: vi.fn(),
    onOpen: vi.fn(),
    onOpenScreener: vi.fn(),
    onScreeners: vi.fn(),
  };
  const view = render(<TopIdeas {...handlers} />);
  return { ...view, ...handlers, grid: () => screen.getByRole('grid', { name: 'Top ideas' }) };
}

stubElementSize();

beforeEach(() => {
  hooks.useIdeas.mockReturnValue(fakeQuery<IdeasData>(data));
});

describe('TopIdeas', () => {
  it("opens a screener's results from its name in a row", async () => {
    const { grid, onOpenScreener } = setup();
    const aapl = within(grid()).getByRole('row', { name: /AAPL/ });
    await userEvent.click(within(aapl).getByRole('button', { name: 'VRP scanner' }));
    expect(onOpenScreener).toHaveBeenCalledWith('vrp');
  });

  it('shows each ticker with its screeners, decision, score, earnings and expiry flag', async () => {
    const { container, grid } = setup();
    const aapl = within(grid()).getByRole('row', { name: /AAPL/ });
    expect(within(aapl).getByText('VRP scanner')).toBeInTheDocument();
    expect(within(aapl).getByText('Liquidity')).toBeInTheDocument();
    expect(within(aapl).getByText('Qualified')).toBeInTheDocument();
    expect(within(aapl).getByText('Earnings first')).toBeInTheDocument();
    expect(within(aapl).getByText('36')).toBeInTheDocument();
    const ko = within(grid()).getByRole('row', { name: /KO/ });
    expect(within(ko).queryByText('Earnings first')).not.toBeInTheDocument();
    expect(screen.getByText('Session 2026-10-02')).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it('shows the display values some screener stored, only as columns that have any', () => {
    const { grid } = setup();
    const headers = within(grid())
      .getAllByRole('columnheader')
      .map((h) => h.textContent)
      .join(' | ');
    expect(headers).toMatch(/IV30.*HV30.*IV \/ HV.*Put ROC/);
    expect(headers).not.toMatch(/Put strike|Put delta|Put premium/);
    const aapl = within(grid()).getByRole('row', { name: /AAPL/ });
    expect(within(aapl).getByText('31.0%')).toBeInTheDocument();
    expect(within(aapl).getByText('1.49')).toBeInTheDocument();
    expect(within(aapl).getByText('1.9%')).toBeInTheDocument();
  });

  it('shows the watch-outs as chips', () => {
    const { grid } = setup();
    const aapl = within(grid()).getByRole('row', { name: /AAPL/ });
    expect(within(aapl).getByText('Earnings before expiry')).toBeInTheDocument();
    const ko = within(grid()).getByRole('row', { name: /KO/ });
    expect(within(ko).getByText('Leveraged / inverse')).toBeInTheDocument();
  });

  it('filters by decision and hides near-term earnings', async () => {
    const user = userEvent.setup();
    setup();
    await user.click(screen.getByRole('button', { name: 'Watch' }));
    expect(screen.queryByRole('row', { name: /AAPL/ })).not.toBeInTheDocument();
    expect(screen.getByRole('row', { name: /KO/ })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Hide earnings < 14d' }));
    expect(screen.getByText('No idea matches these filters.')).toBeInTheDocument();
  });

  it('opens a ticker, and the selected ones, in Explore', async () => {
    const user = userEvent.setup();
    const { onOpen, onCompare } = setup();
    await user.click(screen.getByRole('checkbox', { name: /Select SPY/ }));
    await user.click(screen.getByRole('checkbox', { name: /Select AAPL/ }));
    await user.click(screen.getByRole('button', { name: 'Compare selected (2)' }));
    expect(onCompare).toHaveBeenCalledWith({ sel: 'SPY,AAPL', focus: 'SPY' });
    await user.click(within(screen.getByRole('row', { name: /KO/ })).getByText('KO'));
    expect(onOpen).toHaveBeenCalledWith('KO');
  });

  it('shows loading, empty and error states', async () => {
    hooks.useIdeas.mockReturnValue(fakeQuery<IdeasData>(undefined));
    const loading = setup();
    expect(screen.getByText('Loading ideas…')).toBeInTheDocument();
    await expectNoA11yViolations(loading.container);
    loading.unmount();

    hooks.useIdeas.mockReturnValue(fakeQuery<IdeasData>({ ...data, ideas: [] }));
    const empty = setup();
    expect(screen.getByText('No screener picked anything in this session.')).toBeInTheDocument();
    await expectNoA11yViolations(empty.container);
    empty.unmount();

    hooks.useIdeas.mockReturnValue(fakeQuery<IdeasData>({ ...data, session: null, ideas: [] }));
    const none = setup();
    expect(screen.getByText(/No screener has run yet/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Go to Screeners' }));
    expect(none.onScreeners).toHaveBeenCalledOnce();
    await expectNoA11yViolations(none.container);
    none.unmount();

    hooks.useIdeas.mockReturnValue(
      fakeQuery<IdeasData>(undefined, { isError: true, error: new Error('x') }),
    );
    const failed = setup();
    expect(screen.getByText('The ideas failed to load.')).toBeInTheDocument();
    await expectNoA11yViolations(failed.container);
  });
});
