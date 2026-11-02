import { Box } from '@algotrade/ui';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '@/shared/api';
import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { RollCalculator } from './RollCalculator';

const hooks = vi.hoisted(() => ({ useOptionGrid: vi.fn(), useRollPreview: vi.fn() }));

vi.mock('@/entities/option-grid', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useOptionGrid: hooks.useOptionGrid,
}));
vi.mock('@/features/option-calculators', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useRollPreview: hooks.useRollPreview,
}));
vi.mock('@/features/guide-help', () => ({
  termHelp: (id: string) => `[help ${id}]`,
}));

stubElementSize();

const GRID = {
  instrumentId: 'EQ:X',
  optionGrid: {
    __typename: 'OptionGrid',
    columns: [
      { bucket: 7, expiry: '2026-10-30', days: 7 },
      { bucket: 28, expiry: '2026-11-20', days: 28 },
    ],
  },
};

const row = (strike: number, credit: number, report: boolean | null = false) => ({
  expiry: '2026-11-20',
  strike,
  extra_credit: credit,
  new_breakeven: 78.1,
  credit_per_extra_day: 0.022,
  delta: -0.31,
  report_inside: report,
  report_inside_unknown:
    report === null
      ? {
          code: 'NOT_STORED',
          kind: 'NOT_STORED',
          guide_term: 'unavailable_not_stored',
          kind_text: 'Report date not known',
        }
      : null,
});
const PREVIEW = {
  underlying_id: 'EQ:X',
  session: '2026-10-23',
  priced_at: 79.3,
  right: 'put',
  strike: 80,
  expiry: '2026-10-30',
  sold_at: 1.4,
  buy_back: 1.85,
  over_collected: 0.45,
  above_strike: -0.009,
  days_left: 7,
  delta: -0.4,
  rolls: [row(80, 0.6, true), row(79, 0.5), row(78, 0.4, null), row(77, 0.3), row(76, 0.2)],
};

const mutate = vi.fn();
const mutation = (state: Record<string, unknown> = {}) => ({
  mutate,
  data: undefined,
  isPending: false,
  isError: false,
  error: null,
  ...state,
});

const fill = async (user: ReturnType<typeof userEvent.setup>) => {
  await user.type(screen.getByRole('spinbutton', { name: 'Strike' }), '80');
  await user.selectOptions(screen.getByRole('combobox', { name: 'Expiry' }), '2026-10-30');
  await user.type(screen.getByRole('spinbutton', { name: /Sold at/ }), '1.4');
  await user.tab();
};

beforeEach(() => {
  mutate.mockReset();
  hooks.useOptionGrid.mockReturnValue(fakeQuery(GRID));
  hooks.useRollPreview.mockReturnValue(mutation());
});

describe('RollCalculator', () => {
  it('asks for the strike and the expiry until they are given, then posts what was typed', async () => {
    const user = userEvent.setup();
    render(<RollCalculator symbol="ORBT" onOpenCalls={vi.fn()} />);
    const show = screen.getByRole('button', { name: 'Show rolls' });
    expect(screen.getByText(/Nothing you type is saved/)).toBeInTheDocument();
    await user.click(show);
    expect(mutate).not.toHaveBeenCalled();
    expect(screen.getByText('Enter the strike')).toBeInTheDocument();
    expect(screen.getByText('Pick your put’s expiry')).toBeInTheDocument();
    await fill(user);
    await user.click(show);
    expect(mutate).toHaveBeenCalledWith({
      key: 'ORBT',
      right: 'put',
      strike: 80,
      expiry: '2026-10-30',
      sold_at: 1.4,
      include_debits: false,
      same_delta: false,
    });
  });

  it('offers the expiries the grid lists, with their days', () => {
    render(<RollCalculator symbol="ORBT" onOpenCalls={vi.fn()} />);
    const select = screen.getByRole('combobox', { name: 'Expiry' });
    expect(within(select).getByText('Fri 30 Oct · 7 days')).toBeInTheDocument();
    expect(within(select).getByText(/Fri 20 Nov · 28 days/)).toBeInTheDocument();
  });

  it('shows the sentence, the first four rolls and a report chip, then all of them', async () => {
    const user = userEvent.setup();
    hooks.useRollPreview.mockReturnValue(mutation({ data: { preview: PREVIEW, gap: null } }));
    render(
      <Box as="main">
        <RollCalculator symbol="ORBT" onOpenCalls={vi.fn()} />
      </Box>,
    );
    await fill(user);
    await user.click(screen.getByRole('button', { name: 'Show rolls' }));
    expect(
      screen.getByText(
        'Buying it back now costs $1.85 (middle price): $0.45 a share more than you collected. ORBT is 0.9% below your strike, with 7 days left.',
      ),
    ).toBeInTheDocument();
    const table = screen.getByRole('grid', { name: 'ORBT rolls for a credit' });
    expect(within(table).getAllByRole('row')).toHaveLength(1 + 4);
    expect(within(table).getByText('Includes report')).toBeInTheDocument();
    expect(within(table).getByText('Report date not known')).toBeInTheDocument();
    expect(within(table).getByText('New breakeven')).toBeInTheDocument();
    expect(within(table).queryByText('New delta')).toBeNull();
    await user.click(screen.getByRole('button', { name: 'See all 5' }));
    expect(within(table).getAllByRole('row')).toHaveLength(1 + 5);
    await expectNoA11yViolations(document.body);
  });

  it('adds the More figures and asks again when a choice is toggled', async () => {
    const user = userEvent.setup();
    hooks.useRollPreview.mockReturnValue(mutation({ data: { preview: PREVIEW, gap: null } }));
    render(<RollCalculator symbol="ORBT" onOpenCalls={vi.fn()} />);
    await fill(user);
    await user.click(screen.getByRole('button', { name: 'Show rolls' }));
    await user.click(screen.getByRole('radio', { name: 'More' }));
    expect(screen.getByText('Extra credit per extra day')).toBeInTheDocument();
    expect(screen.getByText('New delta')).toBeInTheDocument();
    mutate.mockClear();
    await user.click(screen.getByRole('checkbox', { name: 'Roll to the same delta' }));
    expect(mutate).toHaveBeenLastCalledWith(expect.objectContaining({ same_delta: true }));
    await user.click(screen.getByRole('checkbox', { name: 'Include rolls that cost money' }));
    expect(mutate).toHaveBeenLastCalledWith(
      expect.objectContaining({ same_delta: true, include_debits: true }),
    );
  });

  it('says why there is no preview in public words, and that an unknown ticker is unknown', async () => {
    const user = userEvent.setup();
    hooks.useRollPreview.mockReturnValue(
      mutation({
        data: {
          preview: null,
          gap: {
            code: 'ILLIQUID',
            kind: 'ILLIQUID',
            guide_term: 'unavailable_illiquid',
            kind_text: 'No two-sided quote for that contract',
          },
        },
      }),
    );
    const { unmount } = render(<RollCalculator symbol="ORBT" onOpenCalls={vi.fn()} />);
    await fill(user);
    await user.click(screen.getByRole('button', { name: 'Show rolls' }));
    expect(screen.getByText('No two-sided quote for that contract')).toBeInTheDocument();
    expect(screen.getByText('[help unavailable_illiquid]')).toBeInTheDocument();
    unmount();
    hooks.useRollPreview.mockReturnValue(
      mutation({ isError: true, error: new ApiError(404, 'unknown') }),
    );
    render(<RollCalculator symbol="ORBT" onOpenCalls={vi.fn()} />);
    await fill(user);
    await user.click(screen.getByRole('button', { name: 'Show rolls' }));
    expect(screen.getByText(/ORBT is not in the reference snapshot/)).toBeInTheDocument();
  });

  it('links to the Calls on shares tab', async () => {
    const user = userEvent.setup();
    const open = vi.fn();
    render(<RollCalculator symbol="ORBT" onOpenCalls={open} />);
    expect(screen.getByText('[help roll_rather_assigned]')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Calls on shares' }));
    expect(open).toHaveBeenCalled();
  });
});
