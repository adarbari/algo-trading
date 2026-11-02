import { Box } from '@algotrade/ui';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { MarginCalculator } from './MarginCalculator';

const hooks = vi.hoisted(() => ({ useOptionGrid: vi.fn(), useMarginPreview: vi.fn() }));

vi.mock('@/entities/option-grid', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useOptionGrid: hooks.useOptionGrid,
}));
vi.mock('@/features/option-calculators', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useMarginPreview: hooks.useMarginPreview,
}));
vi.mock('@/features/guide-help', () => ({
  termHelp: (id: string) => `[help ${id}]`,
}));

stubElementSize();

const GRID = {
  instrumentId: 'EQ:X',
  optionGrid: {
    __typename: 'OptionGrid',
    columns: [{ bucket: 28, expiry: '2026-11-20', days: 28 }],
  },
};

const PREVIEW = {
  underlying_id: 'EQ:X',
  session: '2026-10-23',
  priced_at: 84.2,
  right: 'put',
  strike: 80,
  expiry: '2026-11-20',
  contracts: 2,
  rule: 'reg_t',
  days: 28,
  premium: 1.4,
  premium_total: 280,
  cash_secured: 16000,
  margin_held: 3600,
  premium_over_cash: 0.0175,
  premium_over_margin: 0.0778,
  volume_share: 0.042,
  open_interest_share: 0.0085,
  stress: { episode: 'covid_2020', drop: -0.34, in_the_money: 1200 },
  stress_unknown: null,
};

const mutate = vi.fn();
const reset = vi.fn();
const mutation = (state: Record<string, unknown> = {}) => ({
  mutate,
  reset,
  data: undefined,
  isPending: false,
  isError: false,
  error: null,
  ...state,
});
const withPreview = (extra: Record<string, unknown> = {}) =>
  mutation({ data: { preview: { ...PREVIEW, ...extra }, gap: null } });

const fill = async (user: ReturnType<typeof userEvent.setup>) => {
  await user.type(screen.getByRole('spinbutton', { name: 'Strike' }), '80');
  await user.selectOptions(screen.getByRole('combobox', { name: 'Expiry' }), '2026-11-20');
  await user.type(screen.getByRole('spinbutton', { name: 'Contracts' }), '2');
  await user.tab();
};

beforeEach(() => {
  mutate.mockReset();
  reset.mockReset();
  hooks.useOptionGrid.mockReturnValue(fakeQuery(GRID));
  hooks.useMarginPreview.mockReturnValue(mutation());
});

describe('MarginCalculator', () => {
  it('asks for the strike, expiry and contracts, then posts them', async () => {
    const user = userEvent.setup();
    render(<MarginCalculator symbol="ORBT" />);
    const calculate = screen.getByRole('button', { name: 'Calculate' });
    await user.click(calculate);
    expect(mutate).not.toHaveBeenCalled();
    expect(screen.getByText('Enter the strike')).toBeInTheDocument();
    expect(screen.getByText('Enter whole contracts')).toBeInTheDocument();
    await fill(user);
    await user.click(calculate);
    expect(mutate).toHaveBeenCalledWith({
      key: 'ORBT',
      right: 'put',
      strike: 80,
      expiry: '2026-11-20',
      contracts: 2,
    });
    expect(screen.getByText('Exchange minimum (Reg-T)')).toBeInTheDocument();
    expect(screen.queryByRole('combobox', { name: /broker/i })).toBeNull();
  });

  it('leads with the margin figure, switches to cash-secured, and shows size and stress', async () => {
    const user = userEvent.setup();
    hooks.useMarginPreview.mockReturnValue(withPreview());
    render(
      <Box as="main">
        <MarginCalculator symbol="ORBT" />
      </Box>,
    );
    await fill(user);
    await user.click(screen.getByRole('button', { name: 'Calculate' }));
    expect(screen.getByText('$3,600.00')).toBeInTheDocument();
    expect(screen.getByText('Cash-secured would hold $16,000.00')).toBeInTheDocument();
    expect(screen.getByText("7.8% of what's held, for 28 days")).toBeInTheDocument();
    expect(screen.getByText('$280.00')).toBeInTheDocument();
    expect(screen.getByText("4.2% of today's volume in this contract")).toBeInTheDocument();
    expect(screen.getByText('0.9% of the open contracts at this strike')).toBeInTheDocument();
    expect(screen.getByText(/Covid crash, early 2020, −34%/)).toBeInTheDocument();
    await user.click(screen.getByRole('radio', { name: 'Cash-secured' }));
    expect(screen.getByText('Margin account would hold $3,600.00')).toBeInTheDocument();
    expect(screen.getByText("1.8% of what's held, for 28 days")).toBeInTheDocument();
    await expectNoA11yViolations(document.body);
  });

  it('clears the last result when the contract is edited', async () => {
    const user = userEvent.setup();
    hooks.useMarginPreview.mockReturnValue(withPreview());
    render(<MarginCalculator symbol="ORBT" />);
    await fill(user);
    await user.click(screen.getByRole('button', { name: 'Calculate' }));
    expect(screen.getByText('$3,600.00')).toBeInTheDocument();
    reset.mockClear();
    await user.click(screen.getByRole('radio', { name: 'Call' }));
    expect(reset).toHaveBeenCalled();
    expect(screen.queryByText('$3,600.00')).toBeNull();
  });

  it('hides the parts that are null and says the stress is unknown in public words', async () => {
    const user = userEvent.setup();
    hooks.useMarginPreview.mockReturnValue(
      withPreview({
        volume_share: null,
        open_interest_share: null,
        stress: null,
        stress_unknown: {
          code: 'NOT_STORED',
          kind: 'NOT_STORED',
          guide_term: 'unavailable_not_stored',
          kind_text: 'No market-fall history stored for this stock',
          cause: null,
        },
      }),
    );
    render(<MarginCalculator symbol="ORBT" />);
    await fill(user);
    await user.click(screen.getByRole('button', { name: 'Calculate' }));
    expect(screen.queryByText('Size against trading')).toBeNull();
    expect(screen.getByText('No market-fall history stored for this stock')).toBeInTheDocument();
  });

  it('shows no stress for a call, says why there is no figure, and when the request failed', async () => {
    const user = userEvent.setup();
    hooks.useMarginPreview.mockReturnValue(
      withPreview({ right: 'call', stress: null, stress_unknown: null }),
    );
    const { unmount } = render(<MarginCalculator symbol="ORBT" />);
    await fill(user);
    await user.click(screen.getByRole('button', { name: 'Calculate' }));
    expect(screen.queryByText('If it fell like its worst stored episode')).toBeNull();
    unmount();
    hooks.useMarginPreview.mockReturnValue(mutation({ isError: true, error: new Error('x') }));
    render(<MarginCalculator symbol="ORBT" />);
    await fill(user);
    await user.click(screen.getByRole('button', { name: 'Calculate' }));
    expect(screen.getByText('The ORBT calculator failed to load.')).toBeInTheDocument();
  });
});
