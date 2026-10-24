import { render, screen, within } from '@testing-library/react';
import { useState } from 'react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { filterSearch } from '@/features/filter-bar';
import type { FilterFacets } from '@/entities/filter';
import {
  IDEA_FACTS,
  parseIdeasSearch,
  toIdeasData,
  type IdeasData,
  type IdeasResponse,
} from '@/entities/idea';
import { gql, TestQueryProvider } from '@/shared/api';
import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { TopIdeas, type TopIdeasProps, type TopIdeasSearch } from './TopIdeas';

vi.mock('@/shared/api', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  gql: vi.fn(),
}));

const hooks = vi.hoisted(() => ({ useIdeas: vi.fn() }));
vi.mock('@/entities/idea', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useIdeas: hooks.useIdeas,
}));

type Served = NonNullable<IdeasResponse['ideas']>;
type Item = Served['items'][number];

const pick = (configId: string, decision: string, score: number) => ({
  configId,
  decision,
  score,
  reasons: '',
  flags: [] as string[],
  criteria: [] as { id: string; outcome: string; value: unknown }[],
  columns: [] as { name: string; value: unknown }[],
});
const fact = (name: string, value: unknown, format: 'DATE' | 'NUMBER' | 'PERCENT' | 'FLAG') => ({
  name,
  value,
  unknown:
    value === null
      ? {
          code: 'NULL' as const,
          kind: 'NOT_STORED' as const,
          guideTerm: 'unavailable_not_stored',
          kindText: 'not available for this instrument',
          cause: null,
        }
      : null,
  info: { format, unit: format === 'PERCENT' ? 'decimal' : null, dtype: 'float', nullMeaning: '' },
});
const facts = (
  next: string | null,
  sessions: number | null,
  dte: number | null,
  first: boolean | null,
  iv: number | null = null,
  last: string | null = null,
) => [
  fact(IDEA_FACTS.nextEarnings, next, 'DATE'),
  fact(IDEA_FACTS.lastEarnings, last, 'DATE'),
  fact(IDEA_FACTS.sessionsToEarnings, sessions, 'NUMBER'),
  fact(IDEA_FACTS.expiryDte, dte, 'NUMBER'),
  fact(IDEA_FACTS.earningsBeforeExpiry, first, 'FLAG'),
  fact(IDEA_FACTS.iv30, iv, 'PERCENT'),
  fact(IDEA_FACTS.close, 200.5, 'NUMBER'),
  fact(IDEA_FACTS.ret1d, -0.0123, 'PERCENT'),
  fact(IDEA_FACTS.sectorEtf, 'XLK', 'NUMBER'),
];
/** An idea as the server serves it: its first pick is the best one, every pick is in `pickedBy`. */
const item = (
  rank: number,
  symbol: string,
  picks: ReturnType<typeof pick>[],
  features: ReturnType<typeof facts>,
  watchOut: string[] = [],
): Item => {
  const best = picks[0] as ReturnType<typeof pick>;
  return {
    rank,
    instrumentId: `id-${symbol}`,
    score: 1,
    regime: null,
    sizeMultiplier: null,
    watchOut,
    instrument: { symbol, name: `${symbol} Inc`, features },
    best: {
      configId: best.configId,
      decision: best.decision,
      score: best.score,
      reasons: best.reasons,
      criteria: best.criteria.map(({ id, outcome }) => ({ id, outcome })),
    },
    pickedBy: picks.map((p, index) => ({
      configId: p.configId,
      own: false,
      position: index + 1,
      score: 1 / (index + 1),
      decision: p.decision,
    })),
    metrics: best.columns,
  };
};
const screener = (id: string, name: string) => ({
  screener: { id, name, owner: 'abhinav', version: 1 },
  run: { runId: `run-${id}`, configVersion: 1, paused: 0, coverage: 'COMPLETE', unavailable: [] },
  notRun: null,
  picked: 3,
  withheld: false,
  top: [],
});

const response: IdeasResponse = {
  ideas: {
    session: '2026-10-02',
    total: 4,
    hasMore: false,
    nextCursor: null,
    facets: null,
    pausedTotal: 0,
    paused: [],
    screeners: [screener('vrp', 'VRP scanner'), screener('liq', 'Liquidity')],
    items: [
      item(
        1,
        'AAPL',
        [
          {
            ...pick('vrp', 'QUALIFIED', 84),
            reasons: 'IV rank high, spread tight',
            criteria: [
              { id: 'trend_up', outcome: 'PASS', value: 1 },
              { id: 'iv_rank', outcome: 'NEAR', value: 0.4 },
              { id: 'spread', outcome: 'FAIL', value: 0.9 },
              { id: 'gap', outcome: 'MISSING', value: null },
            ],
            columns: [
              { name: 'hv30', value: 0.21 },
              { name: 'iv_hv_ratio', value: 1.49 },
              { name: 'put_roc', value: 0.019 },
            ],
          },
          pick('liq', 'QUALIFIED', 91),
        ],
        facts('2026-10-29', 19, 36, true, 0.31),
        ['earnings_before_expiry'],
      ),
      item(2, 'KO', [pick('liq', 'WATCH', 66)], facts('2026-10-08', 4, 8, false), [
        'leveraged_inverse',
      ]),
      item(3, 'SPY', [pick('liq', 'QUALIFIED', 88)], facts(null, null, null, null)),
      item(
        4,
        'MRVL',
        [pick('vrp', 'QUALIFIED', 70)],
        facts(null, null, 15, null, null, '2026-08-27'),
      ),
    ],
  },
};
const data = toIdeasData(response);

/** The page's job: the search params held in state, a patch applied to them. */
function Held({
  handlers,
  initial,
}: {
  handlers: Omit<TopIdeasProps, 'search' | 'onSearchChange'>;
  initial: TopIdeasSearch;
}) {
  const [search, setSearch] = useState(initial);
  return (
    <TopIdeas
      {...handlers}
      search={search}
      onSearchChange={(patch) => {
        setSearch((previous) => {
          const next = Object.fromEntries(
            Object.entries({ ...previous, ...patch }).filter(([, value]) => value !== undefined),
          );
          return { ...parseIdeasSearch(next), ...filterSearch(next) };
        });
      }}
    />
  );
}

function setup(initial: TopIdeasSearch = {}) {
  const handlers = {
    onCompare: vi.fn(),
    onOpen: vi.fn(),
    onScreeners: vi.fn(),
  };
  const view = render(
    <TestQueryProvider>
      <Held handlers={handlers} initial={initial} />
    </TestQueryProvider>,
  );
  return { ...view, ...handlers, grid: () => screen.getByRole('grid', { name: 'Top ideas' }) };
}

const option = (value: string, label: string) => ({ value, label });
const FILTER_SET = {
  filterSet: {
    surface: 'ideas',
    label: 'Ideas',
    filters: [
      {
        id: 'decision',
        label: 'Decision',
        group: 'SETUP',
        kind: 'PICK',
        guide: 'term:filter_decision',
        options: [option('QUALIFIED', 'Qualified'), option('WATCH', 'Watch')],
        bins: [],
        windowUnit: null,
      },
      {
        id: 'agreeing',
        label: 'Agreeing screeners',
        group: 'SETUP',
        kind: 'RANGE',
        guide: 'term:filter_agreeing',
        options: [],
        bins: [1, 2, 3],
        windowUnit: null,
      },
      {
        id: 'earnings',
        label: 'Earnings within',
        group: 'COMING_UP',
        kind: 'WINDOW',
        guide: 'term:filter_earnings',
        options: [],
        bins: [],
        windowUnit: 'SESSIONS',
      },
    ],
  },
};
const FACETS: FilterFacets = {
  total: 4,
  matched: 3,
  items: [
    {
      id: 'decision',
      active: true,
      removes: 1,
      unknown: 0,
      options: [
        { value: 'QUALIFIED', count: 3 },
        { value: 'WATCH', count: 1 },
      ],
      bins: [],
    },
    {
      id: 'agreeing',
      active: true,
      removes: null,
      unknown: 2,
      options: [],
      bins: [
        { lo: 1, hi: 2, count: 3 },
        { lo: 2, hi: 3, count: 1 },
      ],
    },
  ],
};
const filtered = (facets: FilterFacets, ideas = data.ideas) =>
  fakeQuery<IdeasData>({ ...data, ideas, facets });

stubElementSize();

beforeEach(() => {
  hooks.useIdeas.mockReset();
  hooks.useIdeas.mockReturnValue(fakeQuery<IdeasData>(data));
  vi.mocked(gql).mockImplementation((document) =>
    Promise.resolve(
      String(document).includes('query FilterSet') ? FILTER_SET : { guideField: null },
    ),
  );
});

describe('TopIdeas', () => {
  it('shows each ticker with its name and sector, why it is here, price and move', () => {
    const { grid } = setup();
    const aapl = within(grid()).getByRole('row', { name: /AAPL/ });
    expect(within(aapl).getByText('AAPL Inc · XLK')).toBeInTheDocument();
    expect(within(aapl).getByText('IV rank high, spread tight')).toHaveAttribute(
      'title',
      'IV rank high, spread tight',
    );
    expect(within(aapl).getByRole('link', { name: 'VRP scanner' })).toBeInTheDocument();
    expect(within(aapl).getByRole('link', { name: /^Liquidity/ })).toBeInTheDocument();
    expect(within(aapl).getByText('200.50')).toBeInTheDocument();
    expect(within(aapl).getByText('−1.2%')).toBeInTheDocument();
    const ko = within(grid()).getByRole('row', { name: /KO/ });
    expect(within(ko).getByRole('link', { name: /^Liquidity/ })).toBeInTheDocument();
    expect(within(ko).queryByRole('link', { name: 'VRP scanner' })).not.toBeInTheDocument();
    expect(within(ko).queryByText(/more/)).not.toBeInTheDocument();
  });

  it('lists the screeners that picked an idea with their place, the best first', () => {
    const { grid } = setup();
    const aapl = within(grid()).getByRole('row', { name: /AAPL/ });
    expect(aapl).toHaveTextContent(/VRP scanner.*Liquidity #2/);
  });

  it('names a withheld screener beside the table, with its help', () => {
    const none = setup();
    expect(none.container).not.toHaveTextContent('Withheld');
    none.unmount();
    const hidden = {
      ...data,
      screeners: data.screeners.map((s) => (s.id === 'liq' ? { ...s, withheld: true } : s)),
    };
    hooks.useIdeas.mockReturnValue(fakeQuery<IdeasData>(hidden));
    const { container } = setup();
    expect(container).toHaveTextContent('Withheld: Liquidity');
  });

  it('gives every row three lines, so the screener names can wrap under the reasons', () => {
    const { grid } = setup();
    expect(grid()).toHaveAttribute('data-lines', '3');
  });

  it('draws one labelled square per criterion of the best pick, under the decision', () => {
    const { grid } = setup();
    const aapl = within(grid()).getByRole('row', { name: /AAPL/ });
    expect(within(aapl).getByRole('img', { name: /^Criteria:/ })).toHaveAccessibleName(
      'Criteria: Trend up: Passed, Iv rank: Near miss, Spread: Missed, Gap: No value',
    );
  });

  it('shows the near-miss reasons under the watch-out badges, with the full text in the title', () => {
    const { grid } = setup();
    const aapl = within(grid()).getByRole('row', { name: /AAPL/ });
    expect(within(aapl).getByTitle('IV rank high, spread tight')).toBeInTheDocument();
  });

  it('keeps the column set in the search params and shows the options set', async () => {
    const user = userEvent.setup();
    const { grid } = setup();
    const headers = () =>
      within(grid())
        .getAllByRole('columnheader')
        .map((h) => h.textContent)
        .join(' | ');
    expect(headers()).toMatch(/Picked by.*Decision.*Score/);
    expect(headers()).not.toMatch(/IV30|Why it's here|Criteria/);
    await user.click(screen.getByRole('radio', { name: 'Options columns' }));
    expect(headers()).toMatch(/IV30.*HV30/);
    expect(headers()).not.toMatch(/Why it's here|Criteria|Price/);
    await user.click(screen.getByRole('radio', { name: 'Stocks columns' }));
    expect(headers()).toMatch(/Price.*Watch out/);
  });

  it("links every screener name in a row to that screener's results, not to the ticker", async () => {
    const { grid, onOpen } = setup();
    const aapl = within(grid()).getByRole('row', { name: /AAPL/ });
    expect(within(aapl).getByRole('link', { name: 'VRP scanner' })).toHaveAttribute(
      'href',
      '/screeners/vrp',
    );
    const liquidity = within(aapl).getByRole('link', { name: /^Liquidity/ });
    expect(liquidity).toHaveAttribute('href', '/screeners/liq');
    await userEvent.click(liquidity);
    expect(onOpen).not.toHaveBeenCalled();
  });

  it('shows the next earnings, else a muted last date, else Unknown', () => {
    const { grid } = setup();
    expect(within(grid()).getByRole('row', { name: /MRVL/ })).toHaveTextContent('Last 27 Aug');
    const spy = within(grid()).getByRole('row', { name: /SPY/ });
    expect(within(spy).getAllByText('Unknown')[0]).toHaveAttribute(
      'title',
      'not available for this instrument',
    );
  });

  it('shows each ticker with its decision, score and expiry flag', async () => {
    const { container, grid } = setup({ columns: 'options' });
    const aapl = within(grid()).getByRole('row', { name: /AAPL/ });
    expect(within(aapl).getByText('Qualified')).toBeInTheDocument();
    expect(within(aapl).getByText('Earnings first')).toBeInTheDocument();
    expect(within(aapl).getByText('36')).toBeInTheDocument();
    const ko = within(grid()).getByRole('row', { name: /KO/ });
    expect(within(ko).queryByText('Earnings first')).not.toBeInTheDocument();
    expect(screen.getByText('Session 2026-10-02')).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it('shows the display values some screener stored, only as columns that have any', () => {
    const { grid } = setup({ columns: 'options' });
    const headers = within(grid())
      .getAllByRole('columnheader')
      .map((h) => h.textContent)
      .join(' | ');
    expect(headers).toMatch(/IV30.*HV30.*IV \/ HV.*Put ROC/);
    expect(headers).not.toMatch(/Put strike|Put delta|Put premium/);
    const aapl = within(grid()).getByRole('row', { name: /AAPL/ });
    expect(within(aapl).getByText('31.0%')).toBeInTheDocument();
    expect(within(aapl).getByText('1.49')).toBeInTheDocument();
    expect(within(aapl).getByText('1.9%')).toBeInTheDocument();
  });

  it('shows the regime size of an idea, only when some run stamped one', () => {
    const none = setup();
    const before = within(none.grid())
      .getAllByRole('columnheader')
      .map((h) => h.textContent);
    expect(before.some((h) => h.startsWith('Size'))).toBe(false);
    none.unmount();
    const stamped = {
      ...data,
      ideas: data.ideas.map((idea) =>
        idea.symbol === 'AAPL' ? { ...idea, regime: 'STRESS', sizeMultiplier: 0.5 } : idea,
      ),
    };
    hooks.useIdeas.mockReturnValue(fakeQuery<IdeasData>(stamped));
    const { grid } = setup();
    const headers = within(grid())
      .getAllByRole('columnheader')
      .map((h) => h.textContent);
    expect(headers.some((h) => h.startsWith('Size'))).toBe(true);
    expect(
      within(within(grid()).getByRole('row', { name: /AAPL/ })).getByText('50%'),
    ).toBeVisible();
  });

  it('offers the next page under the table when the server has more, and not otherwise', async () => {
    const fetchNextPage = vi.fn(() => Promise.resolve());
    hooks.useIdeas.mockReturnValue({
      ...fakeQuery<IdeasData>({ ...data, total: 312, hasMore: true }),
      fetchNextPage,
    });
    const more = setup();
    expect(screen.getByRole('status')).toHaveTextContent(`Showing ${data.ideas.length} of 312`);
    await userEvent.click(screen.getByRole('button', { name: 'Show 50 more' }));
    expect(fetchNextPage).toHaveBeenCalledTimes(1);
    more.unmount();
    hooks.useIdeas.mockReturnValue(fakeQuery<IdeasData>(data));
    setup();
    expect(screen.queryByRole('button', { name: /Show .* more/ })).toBeNull();
  });

  it('keeps "Show more" while the server has more, even when the filters match nothing so far', async () => {
    const fetchNextPage = vi.fn(() => Promise.resolve());
    hooks.useIdeas.mockReturnValue({
      ...fakeQuery<IdeasData>({
        ...data,
        ideas: [],
        total: 312,
        hasMore: true,
        facets: { ...FACETS, matched: 0 },
      }),
      fetchNextPage,
    });
    setup({ f: 'decision:WATCH' });
    expect(await screen.findByText('No ideas match this filter')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Show 50 more' }));
    expect(fetchNextPage).toHaveBeenCalledTimes(1);
  });

  it('shows the watch-outs as chips', () => {
    const { grid } = setup();
    const aapl = within(grid()).getByRole('row', { name: /AAPL/ });
    expect(within(aapl).getByText('Earnings before expiry')).toBeInTheDocument();
    expect(within(aapl).queryByText('Thu 29 Oct')).not.toBeInTheDocument();
    const ko = within(grid()).getByRole('row', { name: /KO/ });
    expect(within(ko).getByText('Leveraged / inverse')).toBeInTheDocument();
  });

  it('asks for the ideas under the filters in the URL, and shows the server rows as they come', () => {
    hooks.useIdeas.mockReturnValue(filtered(FACETS, data.ideas.slice(0, 3)));
    const { grid } = setup({ f: 'decision:QUALIFIED;!agreeing:2..' });
    expect(hooks.useIdeas).toHaveBeenLastCalledWith([
      { id: 'decision', values: ['QUALIFIED'], active: true },
      { id: 'agreeing', min: 2, active: false },
    ]);
    expect(within(grid()).queryByRole('row', { name: /MRVL/ })).not.toBeInTheDocument();
    expect(within(grid()).getByRole('row', { name: /KO/ })).toBeInTheDocument();
  });

  it('shows the applied chips with the rows each removes, and the count line', async () => {
    hooks.useIdeas.mockReturnValue(filtered(FACETS));
    setup({ f: 'decision:QUALIFIED,WATCH;!agreeing:2..' });
    await screen.findByRole('button', { name: 'Setup, 2 active' });
    const chips = screen.getByRole('group', { name: 'Applied filters' });
    expect(within(chips).getByText('Decision Qualified, Watch')).toBeInTheDocument();
    expect(chips).toHaveTextContent('removes 1');
    expect(within(chips).getByText('Agreeing screeners ≥ 2')).toBeInTheDocument();
    expect(chips).toHaveTextContent('2 unknown');
    expect(screen.getAllByText('3 of 4')[0]).toBeInTheDocument();
  });

  it('switches a chip off and back on, removes it, and clears all, through the URL state', async () => {
    const user = userEvent.setup();
    hooks.useIdeas.mockReturnValue(filtered(FACETS));
    setup({ f: 'decision:QUALIFIED;agreeing:2..' });
    await screen.findByRole('button', { name: 'Setup, 2 active' });
    await user.click(screen.getByRole('button', { name: /^Decision Qualified/ }));
    expect(hooks.useIdeas).toHaveBeenLastCalledWith([
      { id: 'decision', values: ['QUALIFIED'], active: false },
      { id: 'agreeing', min: 2, active: true },
    ]);
    await user.click(screen.getByRole('button', { name: /Remove Agreeing screeners/ }));
    expect(hooks.useIdeas).toHaveBeenLastCalledWith([
      { id: 'decision', values: ['QUALIFIED'], active: false },
    ]);
    await user.click(screen.getByRole('button', { name: 'Clear all' }));
    expect(hooks.useIdeas).toHaveBeenLastCalledWith([]);
    expect(screen.queryByRole('group', { name: 'Applied filters' })).not.toBeInTheDocument();
  });

  it('picks a value in a group popover, with the server counts beside the options', async () => {
    const user = userEvent.setup();
    hooks.useIdeas.mockReturnValue(filtered(FACETS));
    setup();
    await user.click(await screen.findByRole('button', { name: 'Setup' }));
    const list = await screen.findByRole('list', { name: 'Decision' });
    expect(within(list).getByRole('button', { name: /Qualified\s*3/ })).toBeInTheDocument();
    await user.click(within(list).getByRole('button', { name: /Watch/ }));
    expect(hooks.useIdeas).toHaveBeenLastCalledWith([
      { id: 'decision', values: ['WATCH'], active: true },
    ]);
  });

  it('says what each recovery chip gives when nothing matches, and switches that filter off', async () => {
    const user = userEvent.setup();
    hooks.useIdeas.mockReturnValue(
      filtered(
        {
          ...FACETS,
          matched: 0,
          items: FACETS.items.map((i) => ({ ...i, removes: i.id === 'decision' ? 31 : 4 })),
        },
        [],
      ),
    );
    setup({ f: 'decision:WATCH;agreeing:5..' });
    expect(await screen.findByText('No ideas match all 2 filters')).toBeInTheDocument();
    const chips = screen.getAllByRole('button', { name: /Switch off .* gives/ });
    expect(chips.map((c) => c.textContent)).toEqual([
      expect.stringContaining('Switch off Decision gives 31'),
      expect.stringContaining('Switch off Agreeing screeners gives 4'),
    ]);
    await user.click(chips[0] as HTMLElement);
    expect(hooks.useIdeas).toHaveBeenLastCalledWith([
      { id: 'decision', values: ['WATCH'], active: false },
      { id: 'agreeing', min: 5, active: true },
    ]);
  });

  it('opens a ticker, and the selected ones, in Explore', async () => {
    const user = userEvent.setup();
    const { onOpen, onCompare } = setup();
    await user.click(screen.getByRole('checkbox', { name: /Select SPY/ }));
    await user.click(screen.getByRole('checkbox', { name: /Select AAPL/ }));
    await user.click(screen.getByRole('button', { name: 'Compare selected (2)' }));
    expect(onCompare).toHaveBeenCalledWith({ sel: 'SPY,AAPL', focus: 'SPY' });
    await user.click(within(screen.getByRole('row', { name: /KO/ })).getByText('KO'));
    expect(onOpen).toHaveBeenCalledWith('KO', 'liq');
  });

  it('shows loading, empty and error states', async () => {
    hooks.useIdeas.mockReturnValue(fakeQuery<IdeasData>(undefined));
    const loading = setup();
    expect(screen.getByText('Loading ideas…')).toBeInTheDocument();
    await expectNoA11yViolations(loading.container);
    loading.unmount();

    hooks.useIdeas.mockReturnValue(fakeQuery<IdeasData>({ ...data, ideas: [] }));
    const empty = setup();
    expect(screen.getByText('No screener picked anything in this session.')).toBeInTheDocument();
    await expectNoA11yViolations(empty.container);
    empty.unmount();

    const notRun = data.screeners.map((s) => ({
      ...s,
      notRun: {
        code: 'NOT_RUN' as const,
        kind: 'NOT_RUN' as const,
        guideTerm: 'not_run',
        kindText: 'not run for this session',
        cause: null,
      },
    }));
    hooks.useIdeas.mockReturnValue(fakeQuery<IdeasData>({ ...data, ideas: [], screeners: notRun }));
    const idle = setup();
    expect(screen.getByText(/No screener has run for this session/)).toBeInTheDocument();
    idle.unmount();

    hooks.useIdeas.mockReturnValue(fakeQuery<IdeasData>({ ...data, session: null, ideas: [] }));
    const none = setup();
    expect(screen.getByText(/No screener has run yet/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Go to Screeners' }));
    expect(none.onScreeners).toHaveBeenCalledOnce();
    await expectNoA11yViolations(none.container);
    none.unmount();

    hooks.useIdeas.mockReturnValue(
      fakeQuery<IdeasData>(undefined, { isError: true, error: new Error('x') }),
    );
    const failed = setup();
    expect(screen.getByText('The ideas failed to load.')).toBeInTheDocument();
    await expectNoA11yViolations(failed.container);
  });
});

describe('TopIdeas field headers', () => {
  it('puts the Guide help button in the field headers and every Ideas column, not in the rank or ticker', async () => {
    const { grid } = setup({ columns: 'options' });
    const help = (name: RegExp) =>
      within(within(grid()).getAllByRole('columnheader', { name })[0] as HTMLElement).queryByRole(
        'button',
        {
          name: /^What is .*\?$/,
        },
      );
    // seven columns' headers plus the Export button's help
    expect(await screen.findAllByRole('button', { name: /^What is .*\?$/ })).toHaveLength(8);
    expect(help(/Expiry DTE/)).toBeVisible();
    expect(help(/IV30/)).toBeVisible();
    expect(help(/Score/)).toBeVisible();
    expect(help(/Decision/)).toBeVisible();
    expect(help(/Picked by/)).toBeVisible();
    expect(help(/Watch out/)).toBeVisible();
    expect(help(/Ticker/)).toBeNull();
  });
});
