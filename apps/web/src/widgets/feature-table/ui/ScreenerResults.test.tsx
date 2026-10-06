import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { ScreenerResults, type ScreenerResultsProps } from './ScreenerResults';

const hooks = vi.hoisted(() => ({
  useScreenerResults: vi.fn(),
  useTableView: vi.fn(),
  change: vi.fn(),
}));

vi.mock('@/entities/screen', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useScreenerResults: hooks.useScreenerResults,
  useRunScreener: () => ({ start: vi.fn(), run: undefined, running: false, error: null }),
}));
vi.mock('@/features/table-view', async (importOriginal) => ({
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
vi.mock('@/entities/explore', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  isStale: () => false,
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
});

function served(total = 2) {
  return {
    session: { date: '2026-10-02', missing: [] },
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
          missing: [],
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

function setup(patch: Partial<ScreenerResultsProps> = {}) {
  const props: ScreenerResultsProps = {
    id: 'vrp',
    onOpen: vi.fn(),
    focusId: null,
    onFocusChange: vi.fn(),
    onToggleCompare: vi.fn(),
    onDismiss: vi.fn(),
    dismissed: new Set(),
    onShowDismissed: vi.fn(),
    ...patch,
  };
  return { props, ...render(<ScreenerResults {...props} />) };
}

const asked = () => hooks.useScreenerResults.mock.lastCall as [string, Record<string, unknown>];

beforeEach(() => {
  hooks.useScreenerResults.mockReset();
  hooks.useScreenerResults.mockReturnValue(fakeQuery(served()));
  hooks.useTableView.mockReturnValue(view());
  hooks.change.mockReset();
});

describe('ScreenerResults', () => {
  it('shows a page of the run from the factories: criteria, display and added columns', async () => {
    const { container } = setup();
    expect(asked()).toEqual([
      'vrp',
      {
        decisions: ['QUALIFIED', 'WATCH', 'LIQUIDITY_RISK', 'EVENT_RISK', 'PAUSED'],
        change: undefined,
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
      'Score',
      'IV30',
      'Spread',
      'Close',
      'Change',
      'Why',
    ])
      expect(within(grid).getByRole('columnheader', { name: new RegExp(header) })).toBeTruthy();
    expect(within(grid).queryByRole('columnheader', { name: /Optionable/ })).toBeNull();
    const aapl = screen.getByRole('row', { name: /AAPL/ });
    expect(aapl).toHaveTextContent('$71.50');
    expect(aapl).toHaveTextContent('New');
    expect(screen.getByRole('row', { name: /KO/ })).toHaveTextContent('Unknown');
    expect(screen.getByText('2 shown · 4,003 in the run')).toBeInTheDocument();
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

  it("has a chip for the paused picks, selected by default, with the run's count", async () => {
    setup();
    const chip = screen.getByRole('button', { name: 'Paused 1' });
    expect(chip).toHaveAttribute('aria-pressed', 'true');
    await userEvent.click(chip);
    expect(hooks.change).toHaveBeenCalledWith({
      decisions: ['QUALIFIED', 'WATCH', 'LIQUIDITY_RISK', 'EVENT_RISK'],
    });
  });

  it('saves a decision chip and the sort into the view; New filters by the change', async () => {
    setup();
    await userEvent.click(screen.getByRole('button', { name: 'Reject 4,000' }));
    expect(hooks.change).toHaveBeenCalledWith({
      decisions: ['QUALIFIED', 'WATCH', 'LIQUIDITY_RISK', 'EVENT_RISK', 'PAUSED', 'REJECT'],
    });
    await userEvent.click(screen.getByRole('button', { name: 'New 1' }));
    expect(asked()[1]).toMatchObject({ change: 'new' });
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
