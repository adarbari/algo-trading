import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { TickerTableData } from '@/entities/explore';
import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { TickerTable, type TickerTableProps } from './TickerTable';

const hooks = vi.hoisted(() => ({
  useTickerTable: vi.fn(),
  useUniverseSize: vi.fn(),
  useFeatureCatalogue: vi.fn(),
  useFeatureDistribution: vi.fn(),
}));

vi.mock('@/entities/explore', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useTickerTable: hooks.useTickerTable,
  useUniverseSize: hooks.useUniverseSize,
}));
vi.mock('@/entities/feature', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useFeatureCatalogue: hooks.useFeatureCatalogue,
  useFeatureDistribution: hooks.useFeatureDistribution,
}));

const IV30 = 'rollup.iv30@v1.iv30';

const table = (session = '2026-10-02'): TickerTableData => ({
  rows: [
    {
      symbol: 'AAPL',
      instrumentId: 'EQ:A',
      name: 'Apple Inc.',
      securityType: 'COMMON_STOCK',
      values: { [IV30]: 0.244 },
    },
    {
      symbol: 'MSFT',
      instrumentId: 'EQ:M',
      name: 'Microsoft',
      securityType: 'COMMON_STOCK',
      values: { [IV30]: 0.294 },
    },
    {
      symbol: 'SPY',
      instrumentId: 'EQ:S',
      name: 'S&P 500 ETF',
      securityType: 'ETF',
      values: { [IV30]: null },
    },
  ],
  total: 3,
  session,
  snapshotDate: session,
  preSnapshot: false,
  missing: [],
  columns: [IV30],
});

const catalogue = [
  {
    name: IV30,
    kind: 'chain',
    source: 'rollups',
    dtype: 'float',
    description: 'Our 30-day ATM implied volatility',
    nullMeaning: '',
    version: 1,
    group: 'iv30@v1',
    key: null,
    inputs: [],
    unit: 'decimal',
    range: null,
    categories: [],
    scope: 'site',
    owner: null,
  },
];

function setup(props: Partial<TickerTableProps> = {}) {
  const handlers = {
    onFiltersChange: vi.fn(),
    onColumnsChange: vi.fn(),
    onSortChange: vi.fn(),
    onSelectedChange: vi.fn(),
    onFocus: vi.fn(),
  };
  const view = render(
    <TickerTable
      filters={{}}
      columns={[IV30]}
      sort={null}
      selected={['MSFT']}
      {...handlers}
      {...props}
    />,
  );
  return { ...view, ...handlers };
}

stubElementSize();

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date('2026-10-03T12:00:00Z'));
  hooks.useTickerTable.mockReturnValue(fakeQuery(table()));
  hooks.useUniverseSize.mockReturnValue(fakeQuery(11_427));
  hooks.useFeatureCatalogue.mockReturnValue(fakeQuery(catalogue));
  hooks.useFeatureDistribution.mockReturnValue(fakeQuery(undefined));
});

describe('TickerTable', () => {
  it('shows tickers with catalogue columns, the count and the selection', async () => {
    const { container } = setup();
    const grid = screen.getByRole('grid', { name: 'Tickers' });
    expect(within(grid).getByRole('columnheader', { name: /IV30/ })).toBeInTheDocument();
    expect(within(grid).getByText('24.4%')).toBeInTheDocument();
    expect(within(grid).getByText('Apple Inc.')).toBeInTheDocument();
    expect(screen.getByText('3 of 11,427 tickers · 1 selected')).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: 'Select MSFT' })).toBeChecked();
    expect(screen.queryByText(/Stale data/)).not.toBeInTheDocument();
    vi.useRealTimers();
    await expectNoA11yViolations(container);
  });

  it('adds ticked rows to the compare set in pick order and focuses a clicked row', async () => {
    vi.useRealTimers();
    const user = userEvent.setup();
    const { onSelectedChange, onFocus } = setup();
    await user.click(screen.getByRole('checkbox', { name: 'Select AAPL' }));
    expect(onSelectedChange).toHaveBeenLastCalledWith(['MSFT', 'AAPL']);
    await user.click(screen.getByText('S&P 500 ETF'));
    expect(onFocus).toHaveBeenLastCalledWith('SPY');
  });

  it('filters locally by the search text', () => {
    setup({ filters: { q: 'micro' } });
    expect(screen.getByText('1 of 11,427 tickers · 1 selected')).toBeInTheDocument();
    expect(screen.queryByText('Apple Inc.')).not.toBeInTheDocument();
  });

  it('turns filter chips into filter changes', async () => {
    vi.useRealTimers();
    const user = userEvent.setup();
    const { onFiltersChange } = setup({ filters: { sector: 'Technology' } });
    await user.click(screen.getByRole('button', { name: 'Optionable' }));
    expect(onFiltersChange).toHaveBeenLastCalledWith({ sector: 'Technology', optionable: true });
    await user.click(screen.getByRole('button', { name: 'Remove Sector: Technology' }));
    expect(onFiltersChange).toHaveBeenLastCalledWith({ sector: undefined });
  });

  it('warns when the session is stale', () => {
    hooks.useTickerTable.mockReturnValue(fakeQuery(table('2026-09-20')));
    setup();
    expect(screen.getByText(/Stale data/)).toBeInTheDocument();
  });

  it('offers a retry when the table fails', async () => {
    vi.useRealTimers();
    const failed = fakeQuery<TickerTableData>(undefined, { isError: true, isPending: false });
    hooks.useTickerTable.mockReturnValue(failed);
    setup();
    await userEvent.setup().click(screen.getByRole('button', { name: /Retry/ }));
    expect(failed.refetch).toHaveBeenCalled();
  });
});
