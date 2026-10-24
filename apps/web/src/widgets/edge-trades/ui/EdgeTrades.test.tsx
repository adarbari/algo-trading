import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { TRADES_FIXTURE, UNKNOWN_FIXTURE } from '@/entities/edge';
import type { FilterFacets } from '@/entities/filter';
import { gql, TestQueryProvider } from '@/shared/api';
import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { EdgeTrades } from './EdgeTrades';

vi.mock('@/shared/api', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  gql: vi.fn(),
}));

const hooks = vi.hoisted(() => ({ useEdgeTrades: vi.fn(), useEdgeLiveStates: vi.fn() }));

vi.mock('@/entities/edge', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useEdgeTrades: hooks.useEdgeTrades,
  useEdgeLiveStates: hooks.useEdgeLiveStates,
}));
vi.mock('@/entities/availability', async () => {
  const { Text } = await import('@algotrade/ui');
  return {
    unknownWord: () => 'Unknown',
    UnknownNote: ({ unknown }: { unknown: { kindText: string } }) => (
      <Text>{unknown.kindText}</Text>
    ),
  };
});
vi.mock('@/features/edge-trades-csv', async () => {
  const { Text } = await import('@algotrade/ui');
  return {
    TradesCsvButton: ({ edgeId, period }: { edgeId: string; period: string }) => (
      <Text>{`csv ${edgeId} ${period}`}</Text>
    ),
  };
});
vi.mock('@/features/guide-help', async () => {
  const { Text } = await import('@algotrade/ui');
  return { termHelp: (id: string) => <Text>{`help ${id}`}</Text> };
});

const option = (value: string, label: string) => ({ value, label });
const FILTER_SET = {
  filterSet: {
    surface: 'edge_trades',
    label: 'Edge trades',
    filters: [
      {
        id: 'result',
        label: 'Result',
        group: 'SETUP',
        kind: 'PICK',
        guide: 'term:filter_trade_result',
        options: [option('won', 'Won'), option('lost', 'Lost')],
        bins: [],
        windowUnit: null,
      },
      {
        id: 'in_sample',
        label: 'In sample',
        group: 'SETUP',
        kind: 'TOGGLE',
        guide: 'term:filter_trade_in_sample',
        options: [],
        bins: [],
        windowUnit: null,
      },
      {
        id: 'record',
        label: 'Backtest or live',
        group: 'SETUP',
        kind: 'PICK',
        guide: 'term:filter_trade_record',
        options: [option('backtest', 'Backtest'), option('live', 'Live')],
        bins: [],
        windowUnit: null,
      },
    ],
  },
};
const FACETS: FilterFacets = {
  total: 3,
  matched: 1,
  items: [
    {
      id: 'result',
      active: true,
      removes: 2,
      unknown: 0,
      options: [
        { value: 'won', count: 1 },
        { value: 'lost', count: 1 },
      ],
      bins: [],
    },
  ],
};

stubElementSize();

function setup() {
  return render(
    <TestQueryProvider>
      <EdgeTrades edgeId="drift" />
    </TestQueryProvider>,
  );
}

const last = () => hooks.useEdgeTrades.mock.calls.at(-1)?.[0] as Record<string, unknown>;

beforeEach(() => {
  hooks.useEdgeTrades.mockReset();
  hooks.useEdgeTrades.mockReturnValue(fakeQuery(TRADES_FIXTURE));
  hooks.useEdgeLiveStates.mockReturnValue(fakeQuery([]));
  vi.mocked(gql).mockImplementation((document) =>
    Promise.resolve(
      String(document).includes('query FilterSet') ? FILTER_SET : { guideField: null },
    ),
  );
});

describe('EdgeTrades', () => {
  it('shows a page of the ledger with the unknown cells in words, not as numbers', async () => {
    const { container } = render(
      <TestQueryProvider>
        <EdgeTrades edgeId="drift" />
      </TestQueryProvider>,
    );
    const table = screen.getByRole('grid', { name: 'Trade ledger' });
    expect(within(table).getByText('AAA')).toBeInTheDocument();
    expect(within(table).queryByText('US-AAA')).not.toBeInTheDocument(); // a ticker, never the id
    expect(within(table).queryByText('US-BBB')).not.toBeInTheDocument(); // unnamed: Unknown, not the id
    expect(within(table).getByText('Licensed')).toBeInTheDocument(); // a personal-licence score
    expect(within(table).getAllByText('Not stored').length).toBeGreaterThan(0);
    expect(within(table).getByText('Excluded')).toBeInTheDocument();
    expect(within(table).getByText('No entry bar')).toBeInTheDocument(); // the public reason
    expect(screen.getByText('3 trades')).toBeInTheDocument();
    expect(screen.getByText(/^Tickers as of /)).toBeInTheDocument(); // the snapshot they came from
    expect(within(table).getAllByText('Unknown').length).toBeGreaterThan(0); // a name with no company: its reason, not blank
    expect(screen.getByText('help trade_ledger')).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it('asks the server for the older default period, another sort and the next page', async () => {
    render(
      <TestQueryProvider>
        <EdgeTrades edgeId="drift" />
      </TestQueryProvider>,
    );
    expect(last()).toMatchObject({ period: 'ALL', page: 1, sort: 'DECISION', descending: false });
    expect(last()['filters']).toEqual([]);
    await userEvent.click(screen.getByRole('button', { name: 'Next' }));
    expect(last()).toMatchObject({ page: 2 });
    await userEvent.click(within(screen.getByRole('grid')).getByRole('button', { name: /^Rank/ }));
    expect(last()).toMatchObject({ sort: 'RANK', page: 1 });
    await userEvent.click(
      within(screen.getByRole('grid')).getByRole('button', { name: /^Ticker/ }),
    );
    expect(last()).toMatchObject({ sort: 'SYMBOL', page: 1 }); // by ticker, not by instrument id
  });

  it('narrows by a filter, starts again at page 1, and clears it', async () => {
    const user = userEvent.setup();
    hooks.useEdgeTrades.mockReturnValue(fakeQuery({ ...TRADES_FIXTURE, facets: FACETS }));
    setup();
    await user.click(screen.getByRole('button', { name: 'Next' }));
    expect(last()).toMatchObject({ page: 2 });
    await user.click(await screen.findByRole('button', { name: 'Setup' }));
    const list = await screen.findByRole('list', { name: 'Result' });
    await user.click(within(list).getByRole('button', { name: /Won\s*1/ }));
    expect(last()).toMatchObject({
      page: 1, // a page of the old filters means nothing under the new ones
      period: 'ALL',
      filters: [{ id: 'result', values: ['won'], active: true }],
    });
    expect(screen.getAllByText('1 of 3')[0]).toBeInTheDocument();
    await user.keyboard('{Escape}');
    await user.click(screen.getByRole('button', { name: 'Clear all' }));
    expect(last()['filters']).toEqual([]);
  });

  it('keeps the bar, with the way back, when the filters match no trade', async () => {
    const user = userEvent.setup();
    hooks.useEdgeTrades.mockReturnValue(
      fakeQuery({
        ...TRADES_FIXTURE,
        rows: [],
        total: 0,
        facets: {
          ...FACETS,
          matched: 0,
          items: FACETS.items.map((i) => ({ ...i, removes: 3 })),
        },
      }),
    );
    setup();
    await user.click(await screen.findByRole('button', { name: 'Setup' }));
    const list = await screen.findByRole('list', { name: 'Result' });
    await user.click(within(list).getByRole('button', { name: /Won/ }));
    await user.keyboard('{Escape}');
    expect(await screen.findByText('No edge trades match this filter')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Switch off Result gives 3/ }));
    expect(last()['filters']).toEqual([{ id: 'result', values: ['won'], active: false }]);
  });

  it('turns the older period tabs into the record and in-sample filters', async () => {
    const user = userEvent.setup();
    setup();
    await user.click(await screen.findByRole('button', { name: 'Setup' }));
    const sample = await screen.findByRole('radiogroup', { name: 'In sample' });
    await user.click(within(sample).getByRole('radio', { name: 'No' }));
    expect(last()['filters']).toEqual([{ id: 'in_sample', values: ['no'], active: true }]);
    expect(screen.getByText('csv drift OUT_OF_SAMPLE')).toBeInTheDocument();
  });

  it('says why Live has no trades for an edge that records no paper trades', () => {
    hooks.useEdgeLiveStates.mockReturnValue(
      fakeQuery([{ edgeId: 'drift', state: 'not_recording', headline: '', followed: false }]),
    );
    render(
      <TestQueryProvider>
        <EdgeTrades edgeId="drift" />
      </TestQueryProvider>,
    );
    expect(screen.getByText('Live: not recording')).toBeInTheDocument();
    expect(screen.getByText('help live_state')).toBeInTheDocument();
  });

  it('hands the period the filters stand for to the CSV button', async () => {
    const user = userEvent.setup();
    render(
      <TestQueryProvider>
        <EdgeTrades edgeId="drift" />
      </TestQueryProvider>,
    );
    expect(screen.getByText('csv drift ALL')).toBeInTheDocument();
    await user.click(await screen.findByRole('button', { name: 'Setup' }));
    const record = await screen.findByRole('list', { name: 'Backtest or live' });
    await user.click(within(record).getByRole('button', { name: /Live/ }));
    expect(screen.getByText('csv drift LIVE')).toBeInTheDocument();
  });

  it('shows the ticker and the company in separate columns', () => {
    render(
      <TestQueryProvider>
        <EdgeTrades edgeId="drift" />
      </TestQueryProvider>,
    );
    const table = screen.getByRole('grid', { name: 'Trade ledger' });
    expect(within(table).getByRole('button', { name: /^Ticker/ })).toBeInTheDocument();
    expect(within(table).getByText('Company')).toBeInTheDocument();
    expect(within(table).getByText('AAA')).toBeInTheDocument();
  });

  it('shows no rows of the previous period under a new selection while it loads', () => {
    // A delayed read: the hook hands back the last page (placeholder data) until the new one lands.
    hooks.useEdgeTrades.mockReturnValue(fakeQuery(TRADES_FIXTURE, { isPlaceholderData: true }));
    const { rerender } = render(
      <TestQueryProvider>
        <EdgeTrades edgeId="drift" />
      </TestQueryProvider>,
    );
    expect(screen.queryByRole('grid', { name: 'Trade ledger' })).not.toBeInTheDocument();
    expect(screen.queryByText('AAA')).not.toBeInTheDocument();
    expect(screen.queryByText('3 trades')).not.toBeInTheDocument();
    expect(screen.getByText('Loading the trades')).toBeInTheDocument();
    hooks.useEdgeTrades.mockReturnValue(fakeQuery(TRADES_FIXTURE));
    rerender(
      <TestQueryProvider>
        <EdgeTrades edgeId="drift" />
      </TestQueryProvider>,
    );
    expect(screen.getByText('3 trades')).toBeInTheDocument();
    expect(screen.getByText('AAA')).toBeInTheDocument();
  });

  it('says why there is no ledger, and that a copy hides its out-of-sample trades', () => {
    hooks.useEdgeTrades.mockReturnValue(
      fakeQuery({ ...TRADES_FIXTURE, rows: [], total: 0, unknown: UNKNOWN_FIXTURE }),
    );
    const { rerender } = render(
      <TestQueryProvider>
        <EdgeTrades edgeId="drift" />
      </TestQueryProvider>,
    );
    expect(screen.getByText('not stored for this run')).toBeInTheDocument();
    expect(screen.queryByRole('grid')).not.toBeInTheDocument();
    hooks.useEdgeTrades.mockReturnValue(
      fakeQuery({ ...TRADES_FIXTURE, rows: [], total: 0, oosHidden: true }),
    );
    rerender(
      <TestQueryProvider>
        <EdgeTrades edgeId="drift" />
      </TestQueryProvider>,
    );
    expect(screen.getByText('Out-of-sample trades hidden')).toBeInTheDocument();
  });

  it('shows loading and failed with a retry', async () => {
    hooks.useEdgeTrades.mockReturnValue(fakeQuery(undefined));
    const { rerender } = render(
      <TestQueryProvider>
        <EdgeTrades edgeId="drift" />
      </TestQueryProvider>,
    );
    expect(screen.getByText('Loading the trades')).toBeInTheDocument();
    const failed = fakeQuery(undefined, { isError: true });
    hooks.useEdgeTrades.mockReturnValue(failed);
    rerender(
      <TestQueryProvider>
        <EdgeTrades edgeId="drift" />
      </TestQueryProvider>,
    );
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(failed.refetch).toHaveBeenCalled();
  });
});
