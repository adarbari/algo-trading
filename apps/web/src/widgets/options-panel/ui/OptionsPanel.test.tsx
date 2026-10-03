import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { OptionChain } from '@/entities/chain';
import { ApiError } from '@/shared/api';
import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { OptionsPanel, type OptionsPanelProps } from './OptionsPanel';

const hooks = vi.hoisted(() => ({ useOptionChain: vi.fn(), useInstrument: vi.fn() }));

vi.mock('@/entities/chain', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useOptionChain: hooks.useOptionChain,
}));
vi.mock('@/entities/instrument', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useInstrument: hooks.useInstrument,
}));

const quote = (strike: number, right: 'P' | 'C', delta: number) => ({
  instrument_id: `OPT:${right}${strike}`,
  expiry: '2026-11-20',
  right,
  strike,
  bid: 2.42,
  ask: 2.61,
  last: 2.5,
  volume: 386,
  open_interest: 19780,
  iv: 0.288,
  delta,
  gamma: 0.0041,
  theta: -0.081,
  vega: 0.33,
  rho: -0.1,
});

const chain: OptionChain = {
  underlying_id: 'EQ:A',
  session: '2026-10-02',
  status: 'OK',
  underlying: { price: 333.6 },
  our_iv: { iv30: 0.244 },
  expiries: ['2026-10-16', '2026-11-20', '2026-12-18'],
  strikes: [300, 320],
  quotes: [quote(300, 'P', -0.12), quote(320, 'P', -0.25), quote(340, 'C', 0.4)],
};

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
  hooks.useInstrument.mockReturnValue(
    fakeQuery({ features: { 'rollup.option_liquidity@v1.target_expiry': '2026-11-20' } }),
  );
  hooks.useOptionChain.mockReturnValue(fakeQuery(chain));
});

describe('OptionsPanel', () => {
  it('opens on the target expiry: puts in plain English with the delta band badged', async () => {
    const { container } = setup();
    expect(hooks.useOptionChain).toHaveBeenLastCalledWith('AAPL', '2026-11-20');
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

  it('waits for the detail before asking for the chain', () => {
    hooks.useInstrument.mockReturnValue(fakeQuery(undefined));
    hooks.useOptionChain.mockReturnValue(fakeQuery(undefined));
    setup();
    expect(hooks.useOptionChain).toHaveBeenLastCalledWith(null, null);
  });

  it('says when the ticker has no chain', () => {
    hooks.useOptionChain.mockReturnValue(
      fakeQuery(undefined, {
        isError: true,
        isPending: false,
        error: new ApiError(404, 'no option chain'),
      }),
    );
    setup();
    expect(screen.getByText('No option chain for AAPL')).toBeInTheDocument();
  });
});
