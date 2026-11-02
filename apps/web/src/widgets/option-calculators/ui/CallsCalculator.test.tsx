import { Box } from '@algotrade/ui';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations, stubElementSize } from '@/shared/lib/testing';

import { CallsCalculator } from './CallsCalculator';

const hooks = vi.hoisted(() => ({ useCallsPreview: vi.fn() }));

vi.mock('@/features/option-calculators', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useCallsPreview: hooks.useCallsPreview,
}));
vi.mock('@/features/guide-help', () => ({
  termHelp: (id: string) => `[help ${id}]`,
}));

stubElementSize();

const row = (strike: number, below: boolean, extra: Record<string, unknown> = {}) => ({
  expiry: '2026-11-20',
  days: 28,
  strike,
  premium: 0.9,
  premium_over_price: 0.0115,
  if_called: 0.052,
  below_price: below,
  report_inside: false,
  report_inside_unknown: null,
  ex_div_before_expiry: false,
  early_exercise_risk: false,
  premium_total: 270,
  ...extra,
});
const PREVIEW = {
  underlying_id: 'EQ:X',
  session: '2026-10-23',
  priced_at: 84.2,
  contracts: 3,
  above_price: 0.073,
  rows: [
    row(77, true),
    row(85, false, { report_inside: true, ex_div_before_expiry: true, early_exercise_risk: true }),
    row(90, false, { premium_total: null }),
  ],
  dividend: { ex_date: '2026-11-12', amount: 0.62, own_by: '2026-11-11' },
  dividend_unknown: null,
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
  await user.type(screen.getByRole('spinbutton', { name: 'Shares you hold' }), '300');
  await user.type(screen.getByRole('spinbutton', { name: /Your price/ }), '78.5');
  await user.tab();
};

beforeEach(() => {
  mutate.mockReset();
  hooks.useCallsPreview.mockReturnValue(mutation());
});

describe('CallsCalculator', () => {
  it('asks for whole shares and a price until they are typed, then posts them', async () => {
    const user = userEvent.setup();
    render(<CallsCalculator symbol="ORBT" />);
    const show = screen.getByRole('button', { name: 'Show calls' });
    await user.click(show);
    expect(mutate).not.toHaveBeenCalled();
    expect(screen.getByText('Enter whole shares')).toBeInTheDocument();
    expect(screen.getByText('Enter your price')).toBeInTheDocument();
    await fill(user);
    await user.click(show);
    expect(mutate).toHaveBeenCalledWith({ key: 'ORBT', shares: 300, price: 78.5 });
  });

  it('shows where the shares closed, the calls with their flags, the muted one labelled, and the dividend', async () => {
    const user = userEvent.setup();
    hooks.useCallsPreview.mockReturnValue(mutation({ data: { preview: PREVIEW, gap: null } }));
    render(
      <Box as="main">
        <CallsCalculator symbol="ORBT" />
      </Box>,
    );
    await fill(user);
    await user.click(screen.getByRole('button', { name: 'Show calls' }));
    expect(screen.getByText('ORBT closed at $84.20, 7.3% above your price.')).toBeInTheDocument();
    const table = screen.getByRole('grid', { name: 'ORBT calls you could sell' });
    expect(within(table).getAllByRole('row')).toHaveLength(1 + 3);
    expect(within(table).getAllByText('below your price')).toHaveLength(1);
    expect(within(table).getByText('Includes report')).toBeInTheDocument();
    expect(within(table).getByText('Ex-dividend before expiry')).toBeInTheDocument();
    expect(within(table).getByText('Early exercise risk')).toBeInTheDocument();
    expect(within(table).getAllByText('$270.00')).toHaveLength(2);
    expect(within(table).getAllByText('1.15%')).toHaveLength(3);
    expect(screen.getByText('3 contracts')).toBeInTheDocument();
    const panel = screen
      .getByRole('heading', { name: 'Dividend and early exercise' })
      .closest('section');
    expect(panel).not.toBeNull();
    expect(
      within(panel as HTMLElement).getByText('Next ex-dividend date 12 Nov 2026, $0.62 a share.'),
    ).toBeInTheDocument();
    expect(
      within(panel as HTMLElement).getByText('Own the shares by 11 Nov 2026 to collect it.'),
    ).toBeInTheDocument();
    await expectNoA11yViolations(document.body);
  });

  it('says the dividend is unknown in public words', async () => {
    const user = userEvent.setup();
    hooks.useCallsPreview.mockReturnValue(
      mutation({
        data: {
          preview: {
            ...PREVIEW,
            dividend: null,
            dividend_unknown: {
              code: 'NOT_STORED',
              kind: 'NOT_STORED',
              guide_term: 'unavailable_not_stored',
              kind_text: 'No dividend announced yet',
            },
          },
          gap: null,
        },
      }),
    );
    render(<CallsCalculator symbol="ORBT" />);
    await fill(user);
    await user.click(screen.getByRole('button', { name: 'Show calls' }));
    expect(screen.getByText('No dividend announced yet')).toBeInTheDocument();
    expect(screen.getByText('[help unavailable_not_stored]')).toBeInTheDocument();
  });

  it('says why there are no calls, and when the request failed', async () => {
    const user = userEvent.setup();
    hooks.useCallsPreview.mockReturnValue(mutation({ isError: true, error: new Error('x') }));
    render(<CallsCalculator symbol="ORBT" />);
    await fill(user);
    await user.click(screen.getByRole('button', { name: 'Show calls' }));
    expect(screen.getByText('The ORBT calculator failed to load.')).toBeInTheDocument();
  });
});
