import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { OptionGrid } from './OptionGrid';

const hooks = vi.hoisted(() => ({ useOptionGrid: vi.fn() }));

vi.mock('@/entities/option-grid', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useOptionGrid: hooks.useOptionGrid,
}));
vi.mock('@/entities/guide', () => ({
  useGuideTerm: (id: string) => ({ data: { entry: { term: `term ${id}` } } }),
}));
vi.mock('@/features/guide-help', () => ({
  termHelp: (id: string) => `[help ${id}]`,
}));

stubElementSize();

const UNKNOWN = {
  __typename: 'Unknown',
  code: 'NOT_STORED',
  kind: 'NOT_STORED',
  guideTerm: 'unavailable_not_stored',
  kindText: 'Not available for this instrument',
};
const cell = (strike: number, yieldAnn: number, openInterest: number | null) => ({
  __typename: 'GridCell',
  band: 0.15,
  strike,
  delta: -0.15,
  iv: 0.4,
  mid: 0.31,
  roc: 0.004,
  yieldAnn,
  breakeven: strike - 0.31,
  pBelow: 0.14,
  spreadPct: 0.06,
  openInterest,
});
const GRID = {
  instrumentId: 'EQ:X',
  optionGrid: {
    __typename: 'OptionGrid',
    underlyingId: 'EQ:X',
    session: '2026-10-23',
    pricedAt: 84.2,
    qKnown: true,
    bands: [0.1, 0.15],
    columns: [
      {
        bucket: 7,
        expiry: '2026-10-30',
        days: 7,
        reportInside: false,
        reportInsideUnknown: null,
        gap: null,
      },
      {
        bucket: 28,
        expiry: '2026-11-20',
        days: 28,
        reportInside: true,
        reportInsideUnknown: null,
        gap: null,
      },
    ],
    puts: [
      [cell(80, 0.071, 1632), cell(81, 0.16, null)],
      [UNKNOWN, cell(76.5, 0.074, 3321)],
    ],
    calls: [
      [cell(90, 0.05, 100), cell(91, 0.06, 100)],
      [cell(92, 0.07, 100), cell(93, 0.08, 100)],
    ],
  },
};

const setup = (data: unknown) => {
  hooks.useOptionGrid.mockReturnValue(fakeQuery(data));
  return render(<OptionGrid symbol="ORBT" />);
};

beforeEach(() => {
  hooks.useOptionGrid.mockReset();
});

describe('OptionGrid', () => {
  it('shows yield a year by delta row and expiry column, flags a report, and names a gap', async () => {
    setup(GRID);
    const grid = screen.getByRole('grid', { name: /ORBT puts yield a year/ });
    expect(within(grid).getByText('Fri 30 Oct')).toBeInTheDocument();
    expect(within(grid).getByText('28 days')).toBeInTheDocument();
    expect(within(grid).getByText('16.0%')).toBeInTheDocument();
    expect(within(grid).getByText('report')).toBeInTheDocument();
    expect(within(grid).getByText('Not available for this instrument')).toBeInTheDocument();
    expect(screen.getByText('Pick a cell to see its figures.')).toBeInTheDocument();
    await expectNoA11yViolations(document.body);
  });

  it('shows the selected cell with every figure named by a Guide term, unknown open interest as a dash', async () => {
    const user = userEvent.setup();
    setup(GRID);
    await user.click(screen.getByRole('gridcell', { name: /16\.0%/ }));
    const detail = screen.getByLabelText('Selected cell');
    expect(within(detail).getByText('term yield_a_year')).toBeInTheDocument();
    expect(within(detail).getByText('$81.00')).toBeInTheDocument();
    expect(within(detail).getByText('—')).toBeInTheDocument();
    expect(within(detail).getByText('[help open_interest]')).toBeInTheDocument();
  });

  it('switches to calls and to the More detail', async () => {
    const user = userEvent.setup();
    setup(GRID);
    await user.click(screen.getByRole('radio', { name: 'More' }));
    expect(screen.getByText(/81\.00 · \$0\.31 · —/)).toBeInTheDocument();
    await user.click(screen.getByRole('radio', { name: 'Calls' }));
    expect(screen.getByRole('grid', { name: /ORBT calls yield/ })).toBeInTheDocument();
    expect(screen.getByText('8.0%')).toBeInTheDocument();
  });

  it('says why there is no grid, by the public kind', () => {
    setup({ instrumentId: 'ETF', optionGrid: UNKNOWN });
    expect(screen.getByText('Not available for this instrument')).toBeInTheDocument();
    expect(screen.getByText('[help unavailable_not_stored]')).toBeInTheDocument();
  });

  it('says so for a ticker outside the snapshot and on a failed read', () => {
    const { unmount } = setup(null);
    expect(screen.getByText(/not in the reference snapshot/)).toBeInTheDocument();
    unmount();
    hooks.useOptionGrid.mockReturnValue({
      ...fakeQuery(undefined),
      isError: true,
      isPending: false,
    });
    render(<OptionGrid symbol="ORBT" />);
    expect(screen.getByText('ORBT option grid failed to load.')).toBeInTheDocument();
  });
});
