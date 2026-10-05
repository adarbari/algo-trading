import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { FeatureTableData, FeatureTableQuery } from '@/entities/feature';
import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { FeatureTable } from './FeatureTable';

const hooks = vi.hoisted(() => ({
  useFeatureTable: vi.fn(),
  useFeatureCatalogue: vi.fn(),
}));

vi.mock('@/entities/feature', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useFeatureTable: hooks.useFeatureTable,
  useFeatureCatalogue: hooks.useFeatureCatalogue,
}));
vi.mock('@/entities/explore', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  isStale: () => false,
}));

stubElementSize();

const EARN = 'rollup.earnings@v1.days_to_earnings';

function served(patch: Partial<FeatureTableData> = {}): FeatureTableData {
  return {
    session: '2026-10-02',
    missing: [],
    preSnapshot: false,
    columns: [
      {
        name: EARN,
        description: 'Sessions to the next report',
        format: 'NUMBER',
        unit: 'days',
        dtype: 'int',
        nullMeaning: 'no report known',
        licence: 'open',
        scope: 'site',
      },
    ],
    rows: [
      {
        symbol: 'AAPL',
        instrumentId: 'EQ:A',
        name: 'Apple Inc.',
        cells: { [EARN]: { value: 23, unknown: null } },
      },
      {
        symbol: 'MRVL',
        instrumentId: 'EQ:M',
        name: 'Marvell',
        cells: { [EARN]: { value: null, unknown: 'NO_PARTITION' } },
      },
    ],
    total: 250,
    page: 1,
    size: 100,
    ...patch,
  };
}

const asked = (): FeatureTableQuery =>
  hooks.useFeatureTable.mock.lastCall?.[0] as FeatureTableQuery;

beforeEach(() => {
  hooks.useFeatureTable.mockReset();
  hooks.useFeatureTable.mockReturnValue(fakeQuery(served()));
  hooks.useFeatureCatalogue.mockReturnValue(fakeQuery([]));
});

describe('FeatureTable', () => {
  it('asks the server for one sorted page and pages through the rest', async () => {
    const user = userEvent.setup();
    const onSortChange = vi.fn();
    const { container } = render(
      <FeatureTable
        label="Tickers"
        columns={[EARN]}
        onColumnsChange={vi.fn()}
        filters={{ leveraged: true }}
        sortMode="server"
        sort={{ columnId: EARN, direction: 'desc' }}
        onSortChange={onSortChange}
        selected={['AAPL']}
        onSelectedChange={vi.fn()}
        emptyMessage="none"
      />,
    );
    expect(asked()).toEqual({
      columns: [EARN],
      keys: undefined,
      filters: { leveraged: true },
      sort: `-${EARN}`,
      page: 1,
      size: 100,
    });
    const grid = screen.getByRole('grid', { name: 'Tickers' });
    expect(within(grid).getByText('23')).toBeInTheDocument();
    expect(within(grid).getByText('Unknown')).toBeInTheDocument(); // MRVL: no partition
    expect(screen.getByText('250 tickers · 1 selected')).toBeInTheDocument();
    expect(screen.getByText('Page 1 of 3')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Next page' }));
    expect(asked().page).toBe(2);
    await user.click(
      within(screen.getByRole('columnheader', { name: /Ticker/ })).getByRole('button'),
    );
    expect(onSortChange).toHaveBeenLastCalledWith({ columnId: 'symbol', direction: 'asc' });
    await expectNoA11yViolations(container);
  });

  it('starts a changed query on its first page', async () => {
    const user = userEvent.setup();
    const props = {
      label: 'Tickers',
      columns: [EARN],
      onColumnsChange: vi.fn(),
      sortMode: 'server' as const,
      emptyMessage: 'none',
    };
    const { rerender } = render(<FeatureTable {...props} filters={{}} />);
    await user.click(screen.getByRole('button', { name: 'Next page' }));
    expect(asked().page).toBe(2);
    rerender(<FeatureTable {...props} filters={{ q: 'mrv' }} />);
    expect(asked().page).toBe(1);
  });

  it('reads the keys asked for in one request and sorts them in the table', () => {
    render(
      <FeatureTable
        label="Side by side"
        keys={['MRVL', 'AAPL']}
        columns={[EARN]}
        onColumnsChange={vi.fn()}
        pickerLabel="Dimension"
        pickerIcon="plus"
        sortMode="client"
        emptyMessage="none"
      />,
    );
    expect(asked()).toEqual({ columns: [EARN], keys: ['MRVL', 'AAPL'], filters: undefined });
    expect(screen.queryByRole('button', { name: 'Next page' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Dimension' })).toBeInTheDocument();
  });

  it('says nothing is stored when the server has no table (an empty store), never loading', () => {
    hooks.useFeatureTable.mockReturnValue(fakeQuery(null));
    render(
      <FeatureTable
        label="Tickers"
        columns={[EARN]}
        onColumnsChange={vi.fn()}
        sortMode="server"
        emptyMessage="none"
      />,
    );
    expect(screen.queryByText(/^Loading/)).toBeNull();
    expect(screen.getAllByText(/Nothing stored yet/).length).toBeGreaterThan(0);
  });

  it('names the tables the session is missing', () => {
    hooks.useFeatureTable.mockReturnValue(
      fakeQuery(served({ missing: ['rollups/instrument/earnings@v1'], preSnapshot: true })),
    );
    render(
      <FeatureTable
        label="Tickers"
        columns={[EARN]}
        onColumnsChange={vi.fn()}
        sortMode="server"
        emptyMessage="none"
      />,
    );
    expect(screen.getByText(/Not stored for 2026-10-02: earnings@v1/)).toBeInTheDocument();
    expect(screen.getByText(/universe snapshot is from after this session/)).toBeInTheDocument();
  });
});
