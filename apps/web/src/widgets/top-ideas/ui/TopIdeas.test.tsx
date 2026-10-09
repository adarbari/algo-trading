import { render, screen, within } from '@testing-library/react';
import { useState } from 'react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  IDEA_FACTS,
  parseIdeasSearch,
  toIdeasData,
  type IdeasData,
  type IdeasResponse,
  type IdeasSearch,
} from '@/entities/idea';
import { gql, TestQueryProvider } from '@/shared/api';
import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { TopIdeas, type TopIdeasProps } from './TopIdeas';

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
const item = (
  rank: number,
  symbol: string,
  picks: ReturnType<typeof pick>[],
  features: ReturnType<typeof facts>,
): Item => ({
  rank,
  instrumentId: `id-${symbol}`,
  regime: null,
  sizeMultiplier: null,
  instrument: { symbol, name: `${symbol} Inc`, features },
  picks,
});
const screener = (id: string, name: string) => ({
  screener: { id, name, owner: 'abhinav', version: 1 },
  run: { runId: `run-${id}`, configVersion: 1, paused: 0 },
  notRun: null,
  picked: 3,
  top: [],
});

const response: IdeasResponse = {
  ideas: {
    session: '2026-10-02',
    priority: ['vrp', 'liq'],
    total: 4,
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
      ),
      item(
        2,
        'KO',
        [{ ...pick('liq', 'WATCH', 66), flags: ['leveraged_inverse'] }],
        facts('2026-10-08', 4, 8, false),
      ),
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
  initial: IdeasSearch;
}) {
  const [search, setSearch] = useState(initial);
  return (
    <TopIdeas
      {...handlers}
      search={search}
      onSearchChange={(patch) => {
        setSearch((previous) =>
          parseIdeasSearch(
            Object.fromEntries(
              Object.entries({ ...previous, ...patch }).filter(([, value]) => value !== undefined),
            ),
          ),
        );
      }}
    />
  );
}

function setup(initial: IdeasSearch = {}) {
  const handlers = {
    onCompare: vi.fn(),
    onOpen: vi.fn(),
    onOpenScreener: vi.fn(),
    onScreeners: vi.fn(),
  };
  const view = render(
    <TestQueryProvider>
      <Held handlers={handlers} initial={initial} />
    </TestQueryProvider>,
  );
  return { ...view, ...handlers, grid: () => screen.getByRole('grid', { name: 'Top ideas' }) };
}

stubElementSize();

beforeEach(() => {
  hooks.useIdeas.mockReturnValue(fakeQuery<IdeasData>(data));
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
    expect(within(aapl).getByRole('button', { name: 'VRP scanner +1 more' })).toBeInTheDocument();
    expect(within(aapl).getByText('200.50')).toBeInTheDocument();
    expect(within(aapl).getByText('−1.2%')).toBeInTheDocument();
    const ko = within(grid()).getByRole('row', { name: /KO/ });
    expect(within(ko).queryByText(/more/)).not.toBeInTheDocument();
  });

  it('draws one labelled square per criterion of the best pick', () => {
    const { grid } = setup();
    const aapl = within(grid()).getByRole('row', { name: /AAPL/ });
    expect(within(aapl).getByRole('img', { name: /^Criteria:/ })).toHaveAccessibleName(
      'Criteria: Trend up: Passed, Iv rank: Near miss, Spread: Missed, Gap: No value',
    );
  });

  it('keeps the column set in the search params and shows the options set', async () => {
    const user = userEvent.setup();
    const { grid } = setup();
    const headers = () =>
      within(grid())
        .getAllByRole('columnheader')
        .map((h) => h.textContent)
        .join(' | ');
    expect(headers()).toMatch(/Why it's here/);
    expect(headers()).not.toMatch(/IV30/);
    await user.click(screen.getByRole('radio', { name: 'Options columns' }));
    expect(headers()).toMatch(/IV30.*HV30/);
    expect(headers()).not.toMatch(/Why it's here|Criteria|Price/);
    await user.click(screen.getByRole('radio', { name: 'Stocks columns' }));
    expect(headers()).toMatch(/Why it's here/);
  });

  it("opens a screener's results from its name in a row", async () => {
    const { grid, onOpenScreener } = setup();
    const aapl = within(grid()).getByRole('row', { name: /AAPL/ });
    await userEvent.click(within(aapl).getByRole('button', { name: 'VRP scanner +1 more' }));
    expect(onOpenScreener).toHaveBeenCalledWith('vrp');
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
    expect(screen.getByText('Session 2026-10-02 · 4 of 4')).toBeInTheDocument();
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

  it('shows the watch-outs as chips', () => {
    const { grid } = setup();
    const aapl = within(grid()).getByRole('row', { name: /AAPL/ });
    expect(within(aapl).getByText('Earnings before expiry')).toBeInTheDocument();
    expect(within(aapl).queryByText('Thu 29 Oct')).not.toBeInTheDocument();
    const ko = within(grid()).getByRole('row', { name: /KO/ });
    expect(within(ko).getByText('Leveraged / inverse')).toBeInTheDocument();
  });

  it('switches the preset view', async () => {
    const user = userEvent.setup();
    setup();
    expect(screen.getByRole('button', { name: 'Top today' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    await user.click(screen.getByRole('button', { name: 'High conviction' }));
    expect(screen.queryByRole('row', { name: /KO/ })).not.toBeInTheDocument();
    expect(screen.getByRole('row', { name: /AAPL/ })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'No earnings soon' }));
    expect(screen.queryByRole('row', { name: /KO/ })).not.toBeInTheDocument();
    expect(screen.getByRole('row', { name: /SPY/ })).toBeInTheDocument();
  });

  it('adds a filter chip, says why nothing matches, and clears the filters', async () => {
    const user = userEvent.setup();
    setup();
    expect(screen.queryByRole('button', { name: 'Clear filters' })).not.toBeInTheDocument();
    await user.click(screen.getAllByRole('button', { name: 'Decision' })[0] as HTMLElement);
    await user.click(screen.getByRole('button', { name: 'Watch' }));
    expect(screen.queryByRole('row', { name: /AAPL/ })).not.toBeInTheDocument();
    expect(screen.getByRole('row', { name: /KO/ })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'High conviction' }));
    expect(screen.getByText('No idea matches High conviction · Decision: Watch.')).toBeVisible();
    await user.click(
      screen.getAllByRole('button', { name: 'Clear filters' }).at(-1) as HTMLElement,
    );
    expect(screen.getByRole('row', { name: /AAPL/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Top today' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });

  it('removes one filter chip with its x', async () => {
    const user = userEvent.setup();
    setup({ screener: 'vrp' });
    expect(screen.queryByRole('row', { name: /KO/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Remove Screener: VRP scanner' }));
    expect(screen.getByRole('row', { name: /KO/ })).toBeInTheDocument();
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
  it('puts the Guide help button in the catalogue field headers, not in the rest', async () => {
    vi.mocked(gql).mockResolvedValue({ guideField: null });
    const { grid } = setup({ columns: 'options' });
    const help = (name: RegExp) =>
      within(within(grid()).getAllByRole('columnheader', { name })[0] as HTMLElement).queryByRole(
        'button',
        {
          name: /^What is .*\?$/,
        },
      );
    expect(await screen.findAllByRole('button', { name: /^What is .*\?$/ })).toHaveLength(2);
    expect(help(/Expiry DTE/)).toBeVisible();
    expect(help(/IV30/)).toBeVisible();
    expect(help(/Score/)).toBeNull();
    expect(help(/Decision/)).toBeNull();
  });
});
