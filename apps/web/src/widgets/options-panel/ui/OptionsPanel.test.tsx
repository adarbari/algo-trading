import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { CHAIN_FACTS, type OptionChain, type OptionQuote } from '@/entities/chain';
import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { OptionsPanel, type OptionsPanelProps } from './OptionsPanel';

const hooks = vi.hoisted(() => ({ useOptionChain: vi.fn(), useOptionQuotes: vi.fn() }));

vi.mock('@/entities/chain', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useOptionChain: hooks.useOptionChain,
  useOptionQuotes: hooks.useOptionQuotes,
}));

const quote = (strike: number, right: 'P' | 'C', delta: number): OptionQuote => ({
  instrumentId: `OPT:${right}${strike}`,
  expiry: '2026-11-20',
  right,
  strike,
  bid: 2.42,
  ask: 2.61,
  last: 2.5,
  volume: 386,
  openInterest: 19780,
  iv: 0.288,
  delta,
  gamma: 0.0041,
  theta: -0.081,
  vega: 0.33,
});

const chain: OptionChain = {
  underlyingId: 'EQ:A',
  session: '2026-10-02',
  status: 'OK',
  expiries: [
    { date: '2026-10-16', days: 14 },
    { date: '2026-11-20', days: 49 },
    { date: '2026-12-18', days: 77 },
  ],
  strikes: [300, 320],
};

const fact = (name: string, value: unknown) => ({
  name,
  value,
  unknown: null,
  info: { format: 'DATE' as const, unit: null, dtype: 'date', nullMeaning: '' },
});

const instrument = (target: string | null, data: OptionChain | null = chain) => ({
  instrumentId: 'EQ:A',
  symbol: 'AAPL',
  features: [
    fact(CHAIN_FACTS.target, target),
    fact(CHAIN_FACTS.spot, 333.6),
    fact(CHAIN_FACTS.iv30, 0.244),
  ],
  chain: data,
});

function setup(props: Partial<OptionsPanelProps> = {}) {
  const handlers = {
    onExpiryChange: vi.fn(),
    onViewChange: vi.fn(),
    onRightChange: vi.fn(),
    onAllStrikesChange: vi.fn(),
  };
  const view = render(
    <OptionsPanel
      symbol="AAPL"
      expiry={null}
      view="simple"
      right="P"
      allStrikes={false}
      {...handlers}
      {...props}
    />,
  );
  return { ...view, ...handlers };
}

stubElementSize();

beforeEach(() => {
  hooks.useOptionChain.mockReturnValue(fakeQuery(instrument('2026-11-20')));
  hooks.useOptionQuotes.mockReturnValue(
    fakeQuery([quote(300, 'P', -0.12), quote(320, 'P', -0.25), quote(340, 'C', 0.4)]),
  );
});

describe('OptionsPanel', () => {
  it('opens on the target expiry: puts in plain English with the delta band badged', async () => {
    const { container } = setup();
    expect(hooks.useOptionChain).toHaveBeenLastCalledWith('AAPL');
    expect(hooks.useOptionQuotes).toHaveBeenLastCalledWith('AAPL', '2026-11-20', '2026-10-02');
    expect(
      screen.getByRole('heading', { name: 'AAPL options · 20 Nov · 49d · puts' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '20 Nov · 49d' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    const grid = screen.getByRole('grid', { name: 'AAPL puts, 2026-11-20' });
    expect(within(grid).getAllByText('8–15 Δ')).toHaveLength(1);
    expect(
      within(grid).getByText(
        /Get paid \$242 now; buy 100 AAPL at \$300 if it falls ~10% by 20 Nov/,
      ),
    ).toBeInTheDocument();
    expect(within(grid).queryByRole('columnheader', { name: /Delta/ })).not.toBeInTheDocument();
    expect(screen.getByText('24.4%')).toBeInTheDocument(); // our IV30: a catalogue feature
    await expectNoA11yViolations(container);
  });

  it('adds IV and the Greeks in Pro, and reports choices', async () => {
    const user = userEvent.setup();
    const { onViewChange, onExpiryChange, onRightChange } = setup({ view: 'pro' });
    const grid = screen.getByRole('grid', { name: 'AAPL puts, 2026-11-20' });
    expect(within(grid).getByRole('columnheader', { name: /Delta/ })).toBeInTheDocument();
    expect(within(grid).getAllByText('28.8%')).toHaveLength(2);
    await user.click(screen.getByRole('radio', { name: 'Simple' }));
    expect(onViewChange).toHaveBeenCalledWith('simple');
    await user.click(screen.getByRole('tab', { name: '18 Dec · 77d' }));
    expect(onExpiryChange).toHaveBeenCalledWith('2026-12-18');
    await user.click(screen.getByRole('radio', { name: 'Calls' }));
    expect(onRightChange).toHaveBeenCalledWith('C');
  });

  it('opens three weeks out when the target expiry is not listed, and reads no quotes before the chain', () => {
    hooks.useOptionChain.mockReturnValue(fakeQuery(instrument(null)));
    setup();
    expect(hooks.useOptionQuotes).toHaveBeenLastCalledWith('AAPL', '2026-11-20', '2026-10-02');
    hooks.useOptionChain.mockReturnValue(fakeQuery(undefined));
    setup();
    expect(hooks.useOptionQuotes).toHaveBeenLastCalledWith(null, null, null);
  });

  it('says when the ticker has no chain for the session', () => {
    hooks.useOptionChain.mockReturnValue(fakeQuery(instrument(null, null)));
    setup();
    expect(screen.getByText('No option chain for AAPL')).toBeInTheDocument();
  });
});
