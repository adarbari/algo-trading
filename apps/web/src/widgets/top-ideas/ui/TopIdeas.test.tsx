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
  tier: 'A',
  klass: 'B',
  reasons: '',
  criteria: [],
  columns: {},
});

const response: IdeasResponse = {
  session: '2026-10-02',
  priority: ['vrp', 'liq'],
  total: 3,
  items: [
    {
      rank: 1,
      instrument_id: 'EQ:A',
      symbol: 'AAPL',
      picks: [pick('vrp', 'QUALIFIED', 84), pick('liq', 'QUALIFIED', 91)],
      next_earnings_date: '2026-10-29',
      days_to_earnings: 27,
      closest_expiry_dte: 36,
      earnings_before_expiry: true,
    },
    {
      rank: 2,
      instrument_id: 'EQ:K',
      symbol: 'KO',
      picks: [pick('liq', 'WATCH', 66)],
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
  const handlers = { onCompare: vi.fn(), onOpen: vi.fn() };
  const view = render(<TopIdeas {...handlers} />);
  return { ...view, ...handlers, grid: () => screen.getByRole('grid', { name: 'Top ideas' }) };
}

stubElementSize();

beforeEach(() => {
  hooks.useIdeas.mockReturnValue(fakeQuery<IdeasData>(data));
});

describe('TopIdeas', () => {
  it('shows each ticker with its screeners, decision, score, earnings and expiry flag', async () => {
    const { container, grid } = setup();
    const aapl = within(grid()).getByRole('row', { name: /AAPL/ });
    expect(within(aapl).getByText('vrp')).toBeInTheDocument();
    expect(within(aapl).getByText('liq')).toBeInTheDocument();
    expect(within(aapl).getByText('Qualified')).toBeInTheDocument();
    expect(within(aapl).getByText('Earnings first')).toBeInTheDocument();
    expect(within(aapl).getByText('36')).toBeInTheDocument();
    expect(within(aapl).getByText('A / B')).toBeInTheDocument();
    const ko = within(grid()).getByRole('row', { name: /KO/ });
    expect(within(ko).queryByText('Earnings first')).not.toBeInTheDocument();
    expect(screen.getByText('Session 2026-10-02')).toBeInTheDocument();
    await expectNoA11yViolations(container);
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

    hooks.useIdeas.mockReturnValue(
      fakeQuery<IdeasData>(undefined, { isError: true, error: new Error('x') }),
    );
    const failed = setup();
    expect(screen.getByText('The ideas failed to load.')).toBeInTheDocument();
    await expectNoA11yViolations(failed.container);
  });
});
