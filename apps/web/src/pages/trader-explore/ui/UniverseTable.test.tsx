import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { decodeFilters } from '@/features/filter-bar';
import { gql, TestQueryProvider } from '@/shared/api';
import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { UniverseTable } from './UniverseTable';

vi.mock('@/shared/api', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  gql: vi.fn(),
}));

const hooks = vi.hoisted(() => ({ useFeatureTable: vi.fn(), useFeatureCatalogue: vi.fn() }));

// The header help button: TableFrame.test.tsx.
vi.mock('@/features/guide-help', () => ({
  helped: ({ help: _help, ...column }: { help?: unknown }) => column,
  termHelp: () => null,
}));
vi.mock('@/entities/feature', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useFeatureTable: hooks.useFeatureTable,
  useFeatureCatalogue: hooks.useFeatureCatalogue,
}));

stubElementSize();

const EARN = 'rollup.earnings@v1.days_to_earnings';
const served = (patch: Record<string, unknown> = {}) => ({
  session: '2026-10-02',
  unavailable: [],
  preSnapshot: false,
  columns: [],
  rows: [
    { symbol: 'AAPL', instrumentId: 'EQ:A', name: 'Apple Inc.', cells: {} },
    { symbol: 'MRVL', instrumentId: 'EQ:M', name: 'Marvell', cells: {} },
  ],
  total: 250,
  page: 1,
  size: 100,
  facets: null,
  ...patch,
});
const asked = () => hooks.useFeatureTable.mock.lastCall?.[0] as Record<string, unknown>;

const option = (value: string, label: string) => ({ value, label });
const FILTER_SET = {
  filterSet: {
    surface: 'universe',
    label: 'Tickers',
    filters: [
      {
        id: 'security_type',
        label: 'Security type',
        group: 'SETUP',
        kind: 'PICK',
        guide: 'term:filter_security_type',
        options: [option('ETF', 'ETF'), option('STOCK', 'Stock')],
        bins: [],
        windowUnit: null,
      },
    ],
  },
};
const FACETS = {
  total: 250,
  matched: 40,
  items: [
    {
      id: 'security_type',
      active: true,
      removes: 210,
      unknown: 0,
      options: [
        { value: 'ETF', count: 40 },
        { value: 'STOCK', count: 0 },
      ],
      bins: [],
    },
  ],
};

/** The route's job: the `f` search param held in state. */
function Held({
  initial,
  onOpen = vi.fn(),
  onCompare = vi.fn(),
}: {
  initial?: string;
  onOpen?: (symbol: string) => void;
  onCompare?: (symbols: string[]) => void;
}) {
  const [f, setF] = useState(initial);
  return (
    <TestQueryProvider>
      <UniverseTable
        f={f}
        onFilterChange={setF}
        columns={[EARN]}
        onColumnsChange={vi.fn()}
        onOpen={onOpen}
        onCompare={onCompare}
      />
    </TestQueryProvider>
  );
}

beforeEach(() => {
  hooks.useFeatureTable.mockReset();
  hooks.useFeatureTable.mockReturnValue(fakeQuery(served()));
  hooks.useFeatureCatalogue.mockReturnValue(fakeQuery([]));
  vi.mocked(gql).mockImplementation((document) =>
    Promise.resolve(
      String(document).includes('query FilterSet') ? FILTER_SET : { guideField: null },
    ),
  );
});

describe('UniverseTable', () => {
  it('asks the server for the first page under the search, and again from page 1 when it changes', async () => {
    const user = userEvent.setup();
    const { container } = render(<Held />);
    await user.click(screen.getByRole('button', { name: 'Next page' }));
    expect(asked()).toMatchObject({ page: 2 });
    await user.type(screen.getByRole('searchbox', { name: 'Find a ticker' }), 'mrv');
    await vi.waitFor(() => {
      expect(asked()).toMatchObject({ q: 'mrv', page: 1 });
    });
    await expectNoA11yViolations(container);
  });

  it('asks under the filters in the URL and shows the server counts with the chips', async () => {
    hooks.useFeatureTable.mockReturnValue(fakeQuery(served({ facets: FACETS })));
    render(<Held initial="security_type:ETF" />);
    expect(asked()['filters']).toEqual(decodeFilters('security_type:ETF'));
    const chips = await screen.findByRole('group', { name: 'Applied filters' });
    expect(await within(chips).findByText('Security type ETF')).toBeInTheDocument();
    expect(chips).toHaveTextContent('removes 210');
    expect(screen.getAllByText('40 of 250')[0]).toBeInTheDocument();
  });

  it('says what each filter gives back when nothing matches, and switches it off', async () => {
    const user = userEvent.setup();
    hooks.useFeatureTable.mockReturnValue(
      fakeQuery(served({ rows: [], total: 0, facets: { ...FACETS, matched: 0 } })),
    );
    render(<Held initial="security_type:ETF" />);
    expect(await screen.findByText('No tickers match this filter')).toBeInTheDocument();
    await user.click(
      await screen.findByRole('button', { name: /Switch off Security type gives 210/ }),
    );
    expect(asked()['filters']).toEqual([{ id: 'security_type', values: ['ETF'], active: false }]);
  });

  it('opens a ticker, and the ticked ones as a compare set', async () => {
    const user = userEvent.setup();
    const onOpen = vi.fn();
    const onCompare = vi.fn();
    render(<Held onOpen={onOpen} onCompare={onCompare} />);
    await user.click(screen.getByRole('checkbox', { name: /Select AAPL/ }));
    await user.click(screen.getByRole('checkbox', { name: /Select MRVL/ }));
    await user.click(screen.getByRole('button', { name: 'Compare selected (2)' }));
    expect(onCompare).toHaveBeenCalledWith(['AAPL', 'MRVL']);
    await user.click(within(screen.getByRole('row', { name: /MRVL/ })).getByText('MRVL'));
    expect(onOpen).toHaveBeenCalledWith('MRVL');
  });
});
