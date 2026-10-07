import type { ChartProps } from '@algotrade/ui';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { FieldGuide, type FieldGuideProps } from './FieldGuide';

const hooks = vi.hoisted(() => ({
  useFeatureCatalogue: vi.fn(),
  useFeatureDistribution: vi.fn(),
  useFeatureHistory: vi.fn(),
  chart: vi.fn(),
}));

vi.mock('@algotrade/ui', async (importOriginal) => {
  const ui = await importOriginal<Record<string, unknown>>();
  const { Text } = await import('@algotrade/ui');
  return {
    ...ui,
    // jsdom has no canvas: the chart is checked by the props it receives.
    Chart: (props: ChartProps) => {
      hooks.chart(props);
      return <Text>{props.label}</Text>;
    },
  };
});
vi.mock('@/entities/feature', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useFeatureCatalogue: hooks.useFeatureCatalogue,
  useFeatureDistribution: hooks.useFeatureDistribution,
}));
vi.mock('@/entities/instrument', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useFeatureHistory: hooks.useFeatureHistory,
}));

const BB = 'rollup.bands@v2.bb_width_pctile_252d';
const SQUEEZE = 'rollup.bands@v2.bb_squeeze';
const RSI = 'rollup.momentum@v1.rsi_14';
const SECTOR = 'instrument.sector';

const info = {
  kind: 'rollup',
  source: 'x',
  dtype: 'float',
  version: 2,
  group: 'bands@v2',
  key: null,
  inputs: ['rollup.price_stats@v2.close'],
  range: [0, 1],
  categories: [],
  scope: 'site',
  owner: null,
  licence: 'open',
  format: 'NUMBER',
  nullMeaning: 'fewer than 240 sessions of history',
};

const catalogue = [
  {
    ...info,
    name: SECTOR,
    dtype: 'str',
    unit: null,
    range: null,
    description: 'GICS sector',
    guide: null,
  },
  {
    ...info,
    name: BB,
    unit: 'decimal',
    description: 'Bandwidth = 4 x the stdev of the last 20 closes over their mean.',
    guide: {
      theme: 'Volatility',
      reads:
        'Where today’s bandwidth sits against the last year, 0 to 1. A squeeze says a big move is likelier.',
      caveats: ['Twenty sessions after a shock day the bands snap shut.'],
      sources: ['Bollinger (2001)'],
      uses: [
        {
          intent: 'A squeeze',
          op: 'lte',
          value: 0.1,
          mode: 'soft',
          tolerance: 0.05,
          onMiss: null,
          note: 'Pair it with a trend.',
        },
        {
          intent: 'A volatile month',
          op: 'gte',
          value: 0.9,
          mode: 'soft',
          tolerance: 0.05,
          onMiss: null,
          note: 'A filter for calm names.',
        },
      ],
    },
  },
  {
    ...info,
    name: SQUEEZE,
    unit: null,
    description: 'Bands inside the channel',
    guide: {
      theme: 'Volatility',
      reads: 'Bands inside the Keltner channel. Quiet.',
      caveats: [],
      sources: [],
      uses: [],
    },
  },
  {
    ...info,
    name: RSI,
    unit: null,
    range: [0, 100],
    description: 'Relative strength',
    guide: {
      theme: 'Momentum and trend',
      reads: 'Relative strength, 0 to 100.',
      caveats: [],
      sources: [],
      uses: [],
    },
  },
];

const distribution = {
  name: BB,
  session: '2026-10-06',
  count: 4812,
  nulls: 12,
  quantiles: [{ q: 0.5, value: 0.45 }],
  histogram: [
    { lo: 0, hi: 0.5, count: 3000 },
    { lo: 0.5, hi: 1, count: 1800 },
  ],
  categories: [],
  unknown: null,
  passing: [
    { intent: 'A squeeze', count: 612, bins: [612, 0] },
    { intent: 'A volatile month', count: 300, bins: [0, 300] },
  ],
};

const props = (patch: Partial<FieldGuideProps> = {}): FieldGuideProps => ({
  theme: undefined,
  field: undefined,
  symbol: undefined,
  defaultSymbol: 'AAPL',
  onThemeChange: vi.fn(),
  onFieldChange: vi.fn(),
  onSymbolChange: vi.fn(),
  onAddToScreen: vi.fn(),
  ...patch,
});

stubElementSize();

beforeEach(() => {
  hooks.chart.mockClear();
  hooks.useFeatureCatalogue.mockReturnValue(fakeQuery(catalogue));
  hooks.useFeatureDistribution.mockReturnValue(fakeQuery(distribution));
  hooks.useFeatureHistory.mockReturnValue({
    series: [
      {
        names: [BB],
        points: [
          { session: '2026-10-05', values: [0.06] },
          { session: '2026-10-06', values: [0.08] },
        ],
      },
    ],
    isPending: false,
  });
});

describe('FieldGuide sidebar', () => {
  it('lists the themes with their counts and the first theme’s fields, Other last', () => {
    render(<FieldGuide {...props()} />);
    const chips = screen.getAllByRole('button').filter((b) => b.hasAttribute('aria-pressed'));
    expect(chips.map((b) => b.textContent)).toEqual([
      'Volatility 2',
      'Momentum and trend 1',
      'Other 1',
    ]);
    expect(screen.getByText('Volatility · 2 fields')).toBeInTheDocument();
    const list = screen.getByRole('list', { name: 'Fields in Volatility' });
    expect(
      within(list)
        .getAllByRole('button')
        .map((b) => b.querySelector('span')?.textContent),
    ).toEqual([BB, SQUEEZE]);
    expect(within(list).getByRole('button', { name: new RegExp(BB) })).toHaveAttribute(
      'aria-current',
      'true',
    );
  });

  it('asks for a theme and for a field', async () => {
    const user = userEvent.setup();
    const p = props();
    render(<FieldGuide {...p} />);
    await user.click(screen.getByRole('button', { name: 'Momentum and trend 1' }));
    expect(p.onThemeChange).toHaveBeenCalledWith('Momentum and trend');
    await user.click(screen.getByRole('button', { name: new RegExp(SQUEEZE) }));
    expect(p.onFieldChange).toHaveBeenCalledWith({ theme: 'Volatility', field: SQUEEZE });
  });

  it('follows the URL: a known field decides its theme', () => {
    render(<FieldGuide {...props({ theme: 'Other', field: RSI })} />);
    expect(screen.getByText('Momentum and trend · 1 field')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 2, name: 'Rsi 14' })).toBeInTheDocument();
  });

  it('searches names, meanings and the guide text, with the counts following the matches', async () => {
    const user = userEvent.setup();
    render(<FieldGuide {...props()} />);
    await user.type(
      screen.getByRole('searchbox', { name: 'Search fields and what they mean' }),
      'keltner',
    );
    expect(screen.getByRole('button', { name: 'Volatility 1' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Momentum and trend 0' })).toBeInTheDocument();
    expect(screen.getByText('Volatility · 1 field')).toBeInTheDocument();
  });

  it('says so when a theme has no field that matches', async () => {
    const user = userEvent.setup();
    render(<FieldGuide {...props()} />);
    await user.type(screen.getByRole('searchbox'), 'zzzz');
    expect(screen.getByText('No field in Volatility matches “zzzz”.')).toBeInTheDocument();
  });
});

describe('FieldGuide detail', () => {
  it('leads with what the number means, then the tags', () => {
    render(<FieldGuide {...props()} />);
    const hero = screen.getByRole('region', { name: 'What this field means' });
    expect(within(hero).getByText(BB)).toBeInTheDocument();
    expect(within(hero).getByRole('heading', { level: 2 })).toBeInTheDocument();
    expect(
      within(hero).getByText(/Where today’s bandwidth sits against the last year/),
    ).toBeInTheDocument();
    for (const tag of [
      'fraction (shown as %) · 0 to 1',
      'rollup · bands@v2',
      'licence open',
      '4,800 names have a value today',
    ]) {
      expect(within(hero).getByText(tag)).toBeInTheDocument();
    }
  });

  it('shows the universe with the passing count from the server, and the criterion can be switched', async () => {
    const user = userEvent.setup();
    render(<FieldGuide {...props()} />);
    expect(screen.getByText('4,800 names with a value · 2026-10-06')).toBeInTheDocument();
    expect(
      screen.getByText('612 names pass “A squeeze” today (lte 0.1 soft tolerance 0.05).'),
    ).toBeInTheDocument();
    expect(screen.getByRole('img', { name: /612 pass “A squeeze”/ })).toBeInTheDocument();
    await user.selectOptions(screen.getByRole('combobox', { name: 'Criterion to highlight' }), '1');
    expect(screen.getByText(/300 names pass “A volatile month” today/)).toBeInTheDocument();
    const last = hooks.chart.mock.lastCall?.[0] as ChartProps;
    expect(last.valueBands).toEqual([{ from: 0.9, tone: 'accent', label: 'A volatile month' }]);
  });

  it('draws the symbol’s last year with the criterion’s zone shaded, the Explore symbol by default', () => {
    render(<FieldGuide {...props()} />);
    expect(hooks.useFeatureHistory).toHaveBeenLastCalledWith(
      'AAPL',
      [BB],
      '2025-10-06',
      '2026-10-06',
    );
    const chart = hooks.chart.mock.lastCall?.[0] as ChartProps;
    expect(chart.series[0]?.points).toEqual([
      { time: '2026-10-05', value: 0.06 },
      { time: '2026-10-06', value: 0.08 },
    ]);
    expect(chart.valueBands).toEqual([{ to: 0.1, tone: 'accent', label: 'A squeeze' }]);
    expect(screen.getByText('Shaded: where “A squeeze” passes.')).toBeInTheDocument();
  });

  it('takes a symbol from the URL, and commits a typed one on Enter', async () => {
    const user = userEvent.setup();
    const p = props({ symbol: 'KO' });
    render(<FieldGuide {...p} />);
    expect(hooks.useFeatureHistory).toHaveBeenLastCalledWith(
      'KO',
      [BB],
      '2025-10-06',
      '2026-10-06',
    );
    const box = screen.getByRole('textbox', { name: 'Symbol' });
    expect(box).toHaveValue('KO');
    await user.clear(box);
    await user.type(box, 'msft{Enter}');
    expect(p.onSymbolChange).toHaveBeenCalledWith('MSFT');
  });

  it('asks for a symbol when there is none', () => {
    render(<FieldGuide {...props({ defaultSymbol: null })} />);
    expect(screen.getByText('Enter a symbol')).toBeInTheDocument();
  });

  it('lists a card per intent and opens the Builder', async () => {
    const user = userEvent.setup();
    const p = props();
    render(<FieldGuide {...p} />);
    const criteria = screen.getByRole('region', { name: 'Criteria by intent' });
    expect(within(criteria).getByText('A squeeze')).toBeInTheDocument();
    expect(within(criteria).getByText('lte 0.1 soft tolerance 0.05')).toBeInTheDocument();
    expect(within(criteria).getByText('Pair it with a trend.')).toBeInTheDocument();
    await user.click(
      within(criteria).getAllByRole('button', { name: 'Add to a screen' })[0] as HTMLElement,
    );
    expect(p.onAddToScreen).toHaveBeenCalledOnce();
  });

  it('warns when the number lies and says how it is computed', () => {
    render(<FieldGuide {...props()} />);
    expect(screen.getByText('When the number lies')).toBeInTheDocument();
    expect(
      screen.getByText('Twenty sessions after a shock day the bands snap shut.'),
    ).toBeInTheDocument();
    const how = screen.getByRole('region', { name: 'How it is computed' });
    expect(within(how).getByText(/Bandwidth = 4 x the stdev/)).toBeInTheDocument();
    expect(
      within(how).getByText('Null when: fewer than 240 sessions of history'),
    ).toBeInTheDocument();
    expect(within(how).getByText('rollup.price_stats@v2.close')).toBeInTheDocument();
    expect(within(how).getByText('Sources: Bollinger (2001)')).toBeInTheDocument();
  });

  it('has no warning, criteria or history for a field the guide does not cover', () => {
    hooks.useFeatureDistribution.mockReturnValue(
      fakeQuery({
        ...distribution,
        name: SECTOR,
        histogram: [],
        quantiles: [],
        categories: [{ value: 'Technology', count: 3 }],
        passing: [],
      }),
    );
    render(<FieldGuide {...props({ theme: 'Other' })} />);
    expect(screen.queryByText('When the number lies')).toBeNull();
    expect(
      screen.getByText('The field guide gives no criterion for this field yet.'),
    ).toBeInTheDocument();
    expect(screen.getByText('No history for this field')).toBeInTheDocument();
    expect(screen.getByText('Technology')).toBeInTheDocument();
  });
});

describe('FieldGuide states', () => {
  it('shows loading and a retry on error for the catalogue', async () => {
    hooks.useFeatureCatalogue.mockReturnValue(fakeQuery(undefined));
    const { rerender } = render(<FieldGuide {...props()} />);
    expect(screen.getByRole('status')).toBeInTheDocument();
    const failed = fakeQuery(undefined, { isError: true });
    hooks.useFeatureCatalogue.mockReturnValue(failed);
    rerender(<FieldGuide {...props()} />);
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(failed.refetch).toHaveBeenCalled();
  });

  it('says so for an empty catalogue', () => {
    hooks.useFeatureCatalogue.mockReturnValue(fakeQuery([]));
    render(<FieldGuide {...props()} />);
    expect(screen.getByText('The catalogue has no fields.')).toBeInTheDocument();
  });

  it('says why nothing is counted when the field is not stored for the session', () => {
    hooks.useFeatureDistribution.mockReturnValue(
      fakeQuery({
        ...distribution,
        count: 0,
        unknown: { code: 'NO_PARTITION', detail: 'bands@v2 has no partition for 2026-10-06' },
        passing: [],
      }),
    );
    render(<FieldGuide {...props()} />);
    expect(screen.getByText('bands@v2 has no partition for 2026-10-06')).toBeInTheDocument();
  });

  it('shows a distribution that failed to load with a retry', async () => {
    const failed = fakeQuery(undefined, { isError: true });
    hooks.useFeatureDistribution.mockReturnValue(failed);
    render(<FieldGuide {...props()} />);
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(failed.refetch).toHaveBeenCalled();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<FieldGuide {...props()} />);
    await expectNoA11yViolations(container);
  });
});
