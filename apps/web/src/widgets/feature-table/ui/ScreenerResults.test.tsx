import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { filterSearch } from '@/features/filter-bar';
import { gql, TestQueryProvider } from '@/shared/api';
import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { ScreenerResults, type ScreenerResultsProps } from './ScreenerResults';

type Gap = {
  kind: 'SYSTEM' | 'NOT_STORED';
  features: string[];
  guideTerm: string;
  cause: null;
};

vi.mock('@/shared/api', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  gql: vi.fn(),
}));

const hooks = vi.hoisted(() => ({
  useScreenerResults: vi.fn(),
  useTableView: vi.fn(),
  change: vi.fn(),
}));

// The header help button: TableFrame.test.tsx.
vi.mock('@/features/guide-help', () => ({
  helped: ({ help: _help, ...column }: { help?: unknown }) => column,
  termHelp: () => null,
}));
vi.mock('@/entities/screen', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useScreenerResults: hooks.useScreenerResults,
  useRunScreener: () => ({ start: vi.fn(), run: undefined, running: false, error: null }),
}));
vi.mock('@/entities/saved-view', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useTableView: hooks.useTableView,
}));
vi.mock('@/entities/feature', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useFeatureCatalogue: () =>
    fakeQuery([
      {
        name: 'feature.vrp_iv30',
        description: 'Lower of IBKR and Cboe IV30',
        format: 'PERCENT',
        unit: 'decimal',
        dtype: 'float64',
        nullMeaning: '',
        licence: 'open',
        scope: 'site',
      },
    ]),
}));

stubElementSize();

const CLOSE = 'rollup.price_stats@v2.close';
const result = (rank: number, symbol: string, decision: string, change: string | null = null) => ({
  instrumentId: `EQ:${symbol}`,
  rank,
  decision,
  score: 100 - rank,
  reasons: decision === 'WATCH' ? 'iv rank near' : '',
  flags: [],
  change,
  previousDecision: change === 'dropped' ? 'QUALIFIED' : null,
  instrument: { instrumentId: `EQ:${symbol}`, symbol, name: `${symbol} Corp` },
  criteria: [
    { id: 'optionable', field: 'instrument.optionable', mode: 'hard', outcome: 'PASS', value: 1 },
    {
      id: 'iv30',
      field: 'feature.vrp_iv30',
      mode: 'hard',
      outcome: rank === 2 ? 'NEAR' : 'PASS',
      value: 0.6,
    },
  ],
  columns: [{ name: 'spread', value: 0.05 }],
  countsToward: [
    {
      edgeId: 'drift',
      edgeName: 'Drift',
      counts: decision === 'QUALIFIED',
      code: decision === 'QUALIFIED' ? 'counts' : 'not_counted',
      topK: 5,
      place: decision === 'QUALIFIED' ? rank : null,
    },
  ],
});

const option = (value: string, label: string) => ({ value, label });
const FILTER_SET = {
  filterSet: {
    surface: 'screener_results',
    label: 'Results',
    filters: [
      {
        id: 'decision',
        label: 'Decision',
        group: 'SETUP',
        kind: 'PICK',
        guide: 'term:filter_result_decision',
        options: [
          option('QUALIFIED', 'Qualified'),
          option('WATCH', 'Watch'),
          option('PAUSED', 'Paused'),
          option('REJECT', 'Reject'),
        ],
        bins: [],
        windowUnit: null,
      },
      {
        id: 'change',
        label: 'Since the previous run',
        group: 'CHANGED',
        kind: 'PICK',
        guide: 'term:filter_change',
        options: [option('new', 'New'), option('dropped', 'Dropped')],
        bins: [],
        windowUnit: null,
      },
    ],
  },
};
const FACETS = {
  total: 4003,
  matched: 2,
  items: [
    {
      id: 'decision',
      active: true,
      removes: 4000,
      unknown: 0,
      options: [
        { value: 'QUALIFIED', count: 1 },
        { value: 'WATCH', count: 1 },
        { value: 'PAUSED', count: 1 },
        { value: 'REJECT', count: 4000 },
      ],
      bins: [],
    },
  ],
};

function served(total = 2) {
  return {
    session: { date: '2026-10-02', unavailable: [] },
    screener: {
      id: 'vrp',
      name: 'VRP',
      criteria: [
        { id: 'optionable', field: 'instrument.optionable', mode: 'hard' },
        { id: 'iv30', field: 'feature.vrp_iv30', mode: 'hard' },
      ],
      displayColumns: [{ name: 'spread', field: 'feature.option_spread' }],
      notRun: null,
      latestRun: {
        runId: 'r1',
        session: '2026-10-02',
        previousSession: '2026-10-01',
        status: 'complete',
        coverage: 'COMPLETE',
        unavailable: [] as Gap[],
        regime: 'STRESS',
        paused: 1,
        decisions: [
          { decision: 'QUALIFIED', count: 1 },
          { decision: 'WATCH', count: 1 },
          { decision: 'PAUSED', count: 1 },
          { decision: 'REJECT', count: 4000 },
        ],
        changes: [
          { change: 'new', count: 1 },
          { change: 'dropped', count: 0 },
        ],
        results: {
          sort: 'rank',
          total,
          page: 1,
          size: 100,
          unavailable: [] as Gap[],
          columns: [
            {
              name: CLOSE,
              description: 'Close',
              format: 'CURRENCY',
              unit: 'usd_per_share',
              dtype: 'float64',
              nullMeaning: '',
              licence: 'open',
              scope: 'site',
            },
          ],
          rows: [[71.5], [null]],
          unknown: [[null], ['NO_ROW']],
          reasons: [[null], [null]],
          kinds: [[null], ['NOT_STORED']],
          facets: FACETS,
          kindTexts: [{ kind: 'NOT_STORED' as const, text: 'not available for this instrument' }],
          results: [result(1, 'AAPL', 'QUALIFIED', 'new'), result(2, 'KO', 'WATCH')],
        },
      },
    },
  };
}

function view(patch: Record<string, unknown> = {}) {
  return {
    scope: 'screener:vrp',
    name: null,
    names: [],
    droppedFilters: [] as string[],
    ready: true,
    columns: [CLOSE],
    sort: null,
    decisions: null,
    change: hooks.change,
    select: vi.fn(),
    saveAs: vi.fn(),
    remove: vi.fn(),
    saving: false,
    removing: false,
    error: null,
    ...patch,
  };
}

/** The route's job: the `f` search param held in state. */
function Held({ props, initial }: { props: ScreenerResultsProps; initial: string | undefined }) {
  const [f, setF] = useState(initial);
  return (
    <ScreenerResults
      {...props}
      f={f}
      onFilterChange={(next) => {
        setF(filterSearch({ f: next }).f);
      }}
    />
  );
}

function setup(patch: Partial<ScreenerResultsProps> = {}, initial?: string) {
  const props: ScreenerResultsProps = {
    id: 'vrp',
    f: undefined,
    onFilterChange: vi.fn(),
    onOpen: vi.fn(),
    focusId: null,
    onFocusChange: vi.fn(),
    onToggleCompare: vi.fn(),
    onDismiss: vi.fn(),
    dismissed: new Set(),
    onShowDismissed: vi.fn(),
    ...patch,
  };
  const view = render(
    <TestQueryProvider>
      <Held props={props} initial={initial} />
    </TestQueryProvider>,
  );
  return { props, ...view };
}

const asked = () => hooks.useScreenerResults.mock.lastCall as [string, Record<string, unknown>];

beforeEach(() => {
  hooks.useScreenerResults.mockReset();
  hooks.useScreenerResults.mockReturnValue(fakeQuery(served()));
  hooks.useTableView.mockReturnValue(view());
  hooks.change.mockReset();
  vi.mocked(gql).mockImplementation((document) =>
    Promise.resolve(
      String(document).includes('query FilterSet') ? FILTER_SET : { guideField: null },
    ),
  );
});

describe('ScreenerResults', () => {
  it('shows a page of the run from the factories: criteria, display and added columns', async () => {
    const { container } = setup({}, 'decision:QUALIFIED,WATCH');
    expect(asked()).toEqual([
      'vrp',
      {
        filters: [{ id: 'decision', values: ['QUALIFIED', 'WATCH'], active: true }],
        q: '',
        columns: [CLOSE],
        sort: undefined,
        page: 1,
        size: 100,
      },
      true,
    ]);
    expect(screen.getByText('Run 2026-10-02 · changes since 2026-10-01')).toBeInTheDocument();
    const grid = screen.getByRole('grid', { name: 'Screener results' });
    for (const header of [
      'Ticker',
      'Decision',
      'Why it matched',
      'Score',
      'Counts toward',
      'IV30',
      'Spread',
      'Close',
      'Change',
      'Why',
    ])
      expect(
        within(grid).getByRole('columnheader', {
          name: new RegExp(header === 'Why' ? '^Why(?! it matched)' : `^${header}`),
        }),
      ).toBeTruthy();
    expect(within(grid).queryByRole('columnheader', { name: /Optionable/ })).toBeNull();
    const aapl = screen.getByRole('row', { name: /AAPL/ });
    expect(aapl).toHaveTextContent('$71.50');
    expect(aapl).toHaveTextContent('New');
    // Why it matched: the rule it passed with its value; Counts toward: the server's verdict per edge.
    expect(aapl).toHaveTextContent('IV30 60.0%');
    expect(aapl).toHaveTextContent('Counts');
    expect(aapl).toHaveTextContent('Drift');
    expect(screen.getByRole('row', { name: /KO/ })).toHaveTextContent('Unknown');
    expect(screen.getAllByText('2 shown · 4,003 in the run')[0]).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it('shows the regime the run stamped in the header, and says so when it stamped none', () => {
    const { unmount } = setup();
    expect(screen.getByText('Regime: Storm')).toBeVisible();
    unmount();
    const none = served();
    hooks.useScreenerResults.mockReturnValue(
      fakeQuery({
        ...none,
        screener: { ...none.screener, latestRun: { ...none.screener.latestRun, regime: null } },
      }),
    );
    setup();
    expect(screen.getByText('Regime: not recorded for this run')).toBeVisible();
  });

  // 2026-10-07: breakout's PARTIAL run lacked trend_stats and vol_stats when it ran; the note
  // named only what the session lacks as read now. Now each is told by kind, never by table.
  it("tells a PARTIAL run's own gaps apart from the session's, by kind", async () => {
    const base = served();
    hooks.useScreenerResults.mockReturnValue(
      fakeQuery({
        ...base,
        session: {
          date: '2026-10-02',
          unavailable: [
            {
              kind: 'NOT_STORED' as const,
              features: ['rollup.fund_reference@v1.aum'],
              guideTerm: 'unavailable_not_stored',
              kindText: 'not available for this instrument',
              cause: null,
            },
          ],
        },
        screener: {
          ...base.screener,
          latestRun: {
            ...base.screener.latestRun,
            status: 'partial',
            coverage: 'PARTIAL',
            unavailable: [
              {
                kind: 'SYSTEM' as const,
                features: ['rollup.trend_stats@v2.trend', 'rollup.vol_stats@v1.vol'],
                guideTerm: 'unavailable_system',
                kindText: 'not available because of a system error',
                cause: null,
              },
            ],
          },
        },
      }),
    );
    setup();
    for (const line of screen.getAllByRole('button', { name: /unavailable/ }))
      await userEvent.click(line);
    expect(
      screen.getByText('The run for 2026-10-02 is PARTIAL; Run now re-runs it.'),
    ).toBeVisible();
    expect(screen.getByText('Not available: system error')).toBeVisible();
    expect(screen.getByText('Not available for this instrument')).toBeVisible();
    expect(screen.queryByText(/rollups\//)).toBeNull();
  });

  // ADR 0055: a COMPLETE run without ibkr_iv (IB Gateway down) looked clean on the page.
  it('warns, by kind, that a COMPLETE run ran without an optional source', async () => {
    const base = served();
    hooks.useScreenerResults.mockReturnValue(
      fakeQuery({
        ...base,
        screener: {
          ...base.screener,
          latestRun: {
            ...base.screener.latestRun,
            unavailable: [
              {
                kind: 'SYSTEM' as const,
                features: ['rollup.ibkr_iv@v1.iv_rank'],
                guideTerm: 'unavailable_system',
                kindText: 'not available because of a system error',
                cause: null,
              },
            ],
          },
        },
      }),
    );
    setup();
    for (const line of screen.getAllByRole('button', { name: /unavailable/ }))
      await userEvent.click(line);
    expect(screen.getByText('Not available: system error')).toBeVisible();
    expect(screen.queryByText('Partial run')).toBeNull();
  });

  it('shows no run banner for a COMPLETE run', () => {
    setup();
    expect(screen.queryByText('Partial run')).toBeNull();
  });

  it('asks for the run under the filters in the URL, and narrows with the bar, saving them into the view', async () => {
    const user = userEvent.setup();
    setup({}, 'decision:QUALIFIED,WATCH,PAUSED');
    const chips = await screen.findByRole('group', { name: 'Applied filters' });
    expect(await within(chips).findByText('Decision Qualified, Watch, Paused')).toBeInTheDocument();
    expect(screen.getAllByText('2 of 4,003')[0]).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'What changed' }));
    const list = await screen.findByRole('list', { name: 'Since the previous run' });
    await user.click(within(list).getByRole('button', { name: /New/ }));
    expect(asked()[1]).toMatchObject({
      filters: [
        { id: 'decision', values: ['QUALIFIED', 'WATCH', 'PAUSED'], active: true },
        { id: 'change', values: ['new'], active: true },
      ],
    });
    expect(hooks.change).toHaveBeenLastCalledWith({
      filters: 'decision:QUALIFIED,WATCH,PAUSED;change:new',
      decisions: [],
    });
  });

  it('reads the view with the f binding: the picks are the default, and a bad definitions read drops none', () => {
    setup();
    const [scope, binding] = hooks.useTableView.mock.lastCall as unknown as [
      string,
      { fallback: (d: string[]) => string; f: string | undefined },
    ];
    expect(scope).toBe('screener:vrp');
    expect(binding.f).toBeUndefined();
    expect(binding.fallback([])).toBe('decision:QUALIFIED,WATCH,LIQUIDITY_RISK,EVENT_RISK,PAUSED');
    expect(binding.fallback(['REJECT'])).toBe('decision:REJECT');
  });

  it('says what each filter gives back when nothing matches, and switches it off', async () => {
    const user = userEvent.setup();
    const none = served();
    hooks.useScreenerResults.mockReturnValue(
      fakeQuery({
        ...none,
        screener: {
          ...none.screener,
          latestRun: {
            ...none.screener.latestRun,
            results: {
              ...none.screener.latestRun.results,
              total: 0,
              rows: [],
              unknown: [],
              reasons: [],
              kinds: [],
              results: [],
              facets: { ...FACETS, matched: 0 },
            },
          },
        },
      }),
    );
    setup({}, 'decision:REJECT');
    expect(await screen.findByText('No results match this filter')).toBeInTheDocument();
    await user.click(
      await screen.findByRole('button', { name: /Switch off Decision gives 4,000/ }),
    );
    expect(asked()[1]).toMatchObject({
      filters: [{ id: 'decision', values: ['REJECT'], active: false }],
    });
  });

  it('saves the sort into the view', async () => {
    setup();
    await userEvent.click(
      within(screen.getByRole('columnheader', { name: /Score/ })).getByRole('button'),
    );
    expect(String((hooks.change.mock.lastCall?.[0] as { sort?: string }).sort)).toMatch(/score$/);
  });

  it('pages through a long run and hides the dismissed rows', async () => {
    hooks.useScreenerResults.mockReturnValue(fakeQuery(served(250)));
    setup({ dismissed: new Set(['EQ:KO']) });
    expect(screen.queryByRole('row', { name: /KO/ })).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: 'Next page' }));
    expect(asked()[1]).toMatchObject({ page: 2 });
  });

  it('renders the detail of the row under review beside the table', () => {
    const renderDetail = vi.fn(() => null);
    setup({ renderDetail, focusId: 'EQ:KO' });
    const [focus] = renderDetail.mock.lastCall as unknown as [{ row: { symbol: string } }];
    expect(focus.row.symbol).toBe('KO');
  });

  it('on a phone opens the chosen row in a sheet, never the first-row fallback', async () => {
    vi.stubGlobal('innerWidth', 375);
    try {
      const renderDetail = vi.fn(() => 'pick detail');
      const { props, rerender } = setup({ renderDetail });
      expect(screen.queryByRole('dialog')).toBeNull();
      rerender(
        <TestQueryProvider>
          <Held props={{ ...props, focusId: 'EQ:KO' }} initial={undefined} />
        </TestQueryProvider>,
      );
      expect(screen.getByRole('dialog', { name: 'KO' })).toHaveTextContent('pick detail');
      await userEvent.keyboard('{Escape}');
      expect(props.onFocusChange).toHaveBeenLastCalledWith(null);
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it('says when the screener has no run for the session', () => {
    const none = served();
    hooks.useScreenerResults.mockReturnValue(
      fakeQuery({ ...none, screener: { ...none.screener, latestRun: null } }),
    );
    setup();
    expect(
      screen.getByText(
        'No run stored for this screener on 2026-10-02. Run it now to see what it picks.',
      ),
    ).toBeInTheDocument();
  });
});
