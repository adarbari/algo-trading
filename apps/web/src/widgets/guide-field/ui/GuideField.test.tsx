import type { ChartProps } from '@algotrade/ui';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { GuideField } from './GuideField';

const hooks = vi.hoisted(() => ({
  useFeatureCatalogue: vi.fn(),
  useFeatureDistribution: vi.fn(),
  useFeatureHistory: vi.fn(),
  useGuideField: vi.fn(),
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
vi.mock('@/entities/guide', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useGuideField: hooks.useGuideField,
}));
vi.mock('@/entities/instrument', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useFeatureHistory: hooks.useFeatureHistory,
}));

const BB = 'rollup.bands@v2.bb_width_pctile_252d';
const SQUEEZE = 'rollup.bands@v2.bb_squeeze';
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
      theme: 'volatility',
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
      theme: 'volatility',
      reads: 'Bands inside the Keltner channel. Quiet.',
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

const plain = (text: string) => ({ segments: [{ text }] });

const derived = {
  readsLinked: {
    segments: [
      { text: 'Where today’s bandwidth sits against ', field: null },
      { text: SQUEEZE, field: SQUEEZE },
      { text: ', 0 to 1.', field: null },
    ],
  },
  caveatsLinked: [
    {
      segments: [
        { text: 'Twenty sessions after a shock day, check ', field: null },
        { text: SECTOR, field: SECTOR },
        { text: ' first.', field: null },
      ],
    },
  ],
  related: [SQUEEZE],
  playbooks: [
    {
      id: 'breakout',
      name: 'Breakout',
      family: 'breakouts',
      rules: ['lte 0.1 soft'],
      column: false,
    },
  ],
  situations: [
    {
      name: 'Earnings gap inside the window',
      slug: 'earnings-gap',
      signsLinked: plain('a gap resets the bands'),
    },
  ],
};

stubElementSize();

beforeEach(() => {
  hooks.chart.mockClear();
  hooks.useFeatureCatalogue.mockReturnValue(fakeQuery(catalogue));
  hooks.useFeatureDistribution.mockReturnValue(fakeQuery(distribution));
  hooks.useGuideField.mockReturnValue(fakeQuery(derived));
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

const anchor = (id: string) => {
  const found = document.getElementById(id);
  if (!found) throw new Error(`no section ${id}`);
  return found;
};

const setup = (name = BB, onAddToBuilder = vi.fn()) => {
  render(<GuideField name={name} onAddToBuilder={onAddToBuilder} />);
  return { onAddToBuilder };
};

describe('GuideField sections', () => {
  it('has the sections in the fixed order, each anchored', () => {
    setup();
    const ids = ['reads', 'universe', 'use', 'lies', 'computed', 'related', 'ticker', 'sources'];
    const anchors = [...document.querySelectorAll('[id]')]
      .map((e) => e.id)
      .filter((id) => ids.includes(id));
    expect(anchors).toEqual(ids);
  });

  it('leads with what the number means as the page heading, then the tags', () => {
    setup();
    const hero = screen.getByRole('region', { name: 'What this field means' });
    expect(within(hero).getByText(BB)).toBeInTheDocument();
    expect(within(hero).getByRole('heading', { level: 1 })).toBeInTheDocument();
    expect(within(hero).getByText(/Where today’s bandwidth sits against/)).toBeInTheDocument();
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
    setup();
    expect(screen.getByText('4,800 names with a value · 2026-10-06')).toBeInTheDocument();
    expect(
      screen.getByText('612 names pass “A squeeze” today (lte 0.1 soft tolerance 0.05).'),
    ).toBeInTheDocument();
    expect(screen.getByRole('img', { name: /612 pass “A squeeze”/ })).toBeInTheDocument();
    await user.selectOptions(screen.getByRole('combobox', { name: 'Criterion to highlight' }), '1');
    expect(screen.getByText(/300 names pass “A volatile month” today/)).toBeInTheDocument();
  });

  it('lists a card per intent and opens the Builder', async () => {
    const user = userEvent.setup();
    const { onAddToBuilder } = setup();
    const use = screen.getByRole('region', { name: 'Use it for' });
    expect(within(use).getByText('A squeeze')).toBeInTheDocument();
    expect(within(use).getByText('lte 0.1 soft tolerance 0.05')).toBeInTheDocument();
    expect(within(use).getByText('Pair it with a trend.')).toBeInTheDocument();
    await user.click(
      within(use).getAllByRole('button', { name: 'Add to Builder' })[0] as HTMLElement,
    );
    expect(onAddToBuilder).toHaveBeenCalledOnce();
  });

  it('warns when it lies and names the situations that fool it', () => {
    setup();
    const lies = anchor('lies');
    expect(within(lies).getByText(/Twenty sessions after a shock day, check/)).toBeInTheDocument();
    expect(within(lies).getByText('Situations that fool it')).toBeInTheDocument();
    expect(
      within(lies).getByRole('link', { name: 'Earnings gap inside the window' }),
    ).toHaveAttribute('href', '/guide/situations/earnings-gap');
  });

  it('links the field names in how to read it and in the caveats to their pages', () => {
    setup();
    expect(within(anchor('reads')).getByRole('link', { name: SQUEEZE })).toHaveAttribute(
      'href',
      `/guide/fields/${encodeURIComponent(SQUEEZE)}`,
    );
    expect(within(anchor('lies')).getByRole('link', { name: SECTOR })).toHaveAttribute(
      'href',
      `/guide/fields/${encodeURIComponent(SECTOR)}`,
    );
  });

  it('shows the guide’s plain text for reads and caveats until the server’s linked text arrives', () => {
    hooks.useGuideField.mockReturnValue(fakeQuery(undefined));
    setup();
    expect(
      within(anchor('reads')).getByText(/Where today’s bandwidth sits against the last year/),
    ).toBeInTheDocument();
    expect(
      within(anchor('lies')).getByText('Twenty sessions after a shock day the bands snap shut.'),
    ).toBeInTheDocument();
    expect(within(anchor('reads')).queryByRole('link')).toBeNull();
  });

  it('says how it is computed, without the sources (they have their own section)', () => {
    setup();
    const how = screen.getByRole('region', { name: 'How it is computed' });
    expect(within(how).getByText(/Bandwidth = 4 x the stdev/)).toBeInTheDocument();
    expect(
      within(how).getByText('Null when: fewer than 240 sessions of history'),
    ).toBeInTheDocument();
    expect(within(how).getByText('rollup.price_stats@v2.close')).toBeInTheDocument();
    expect(within(how).queryByText(/Bollinger/)).toBeNull();
    const sources = anchor('sources');
    expect(within(sources).getByText('Bollinger (2001)')).toBeInTheDocument();
  });

  it('links related fields and the playbooks that use it to their pages', () => {
    setup();
    const related = screen.getByRole('region', { name: 'Related fields and playbooks' });
    expect(within(related).getByRole('link', { name: SQUEEZE })).toHaveAttribute(
      'href',
      `/guide/fields/${encodeURIComponent(SQUEEZE)}`,
    );
    expect(within(related).getByRole('link', { name: 'Breakout' })).toHaveAttribute(
      'href',
      '/guide/playbooks/breakout',
    );
    expect(within(related).getByText('lte 0.1 soft')).toBeInTheDocument();
  });

  it('asks for a symbol, then draws its year and links to Explore with the field', async () => {
    const user = userEvent.setup();
    setup();
    expect(screen.getByText('Enter a symbol')).toBeInTheDocument();
    await user.type(screen.getByRole('textbox', { name: 'Symbol' }), 'msft{Enter}');
    expect(hooks.useFeatureHistory).toHaveBeenLastCalledWith(
      'MSFT',
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
    const link = screen.getByRole('link', { name: 'Open in Explore with its history' });
    const href = new URL(link.getAttribute('href') ?? '', 'http://x');
    expect(href.pathname).toBe('/explore');
    expect(Object.fromEntries(href.searchParams)).toEqual({
      sel: 'MSFT',
      focus: 'MSFT',
      tab: 'features',
      feature: BB,
    });
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
    hooks.useGuideField.mockReturnValue(
      fakeQuery({
        readsLinked: null,
        caveatsLinked: [],
        related: [],
        playbooks: [],
        situations: [],
      }),
    );
    setup(SECTOR);
    expect(screen.getByText('The guide lists no caveat for this field yet.')).toBeInTheDocument();
    expect(
      screen.getByText('The field guide gives no criterion for this field yet.'),
    ).toBeInTheDocument();
    expect(screen.getByText('No history for this field')).toBeInTheDocument();
    expect(screen.getByText('The guide names no related field.')).toBeInTheDocument();
    expect(screen.getByText('The guide cites no source for this field.')).toBeInTheDocument();
    expect(screen.getByText('Technology')).toBeInTheDocument();
  });
});

describe('GuideField states', () => {
  it('shows loading and a retry on error for the catalogue', async () => {
    hooks.useFeatureCatalogue.mockReturnValue(fakeQuery(undefined));
    const { rerender } = render(<GuideField name={BB} onAddToBuilder={vi.fn()} />);
    expect(screen.getByRole('status')).toBeInTheDocument();
    const failed = fakeQuery(undefined, { isError: true });
    hooks.useFeatureCatalogue.mockReturnValue(failed);
    rerender(<GuideField name={BB} onAddToBuilder={vi.fn()} />);
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(failed.refetch).toHaveBeenCalled();
  });

  it('says so for a name the catalogue does not have', () => {
    setup('feature.nope');
    expect(screen.getByText('No such field')).toBeInTheDocument();
    expect(screen.getByText('The catalogue has no field called feature.nope.')).toBeInTheDocument();
  });

  it('says why nothing is counted when the field is not stored for the session', () => {
    hooks.useFeatureDistribution.mockReturnValue(
      fakeQuery({
        ...distribution,
        count: 0,
        unknown: {
          code: 'NO_PARTITION',
          kind: 'SYSTEM',
          guideTerm: 'unavailable_system',
          kindText: 'not available because of a system error',
          cause: null,
        },
        passing: [],
      }),
    );
    setup();
    expect(
      screen.getByText('Nothing is counted: not available because of a system error.'),
    ).toBeInTheDocument();
  });

  it('shows the server-derived parts loading and failing on their own', async () => {
    hooks.useGuideField.mockReturnValue(fakeQuery(undefined));
    const { unmount } = render(<GuideField name={BB} onAddToBuilder={vi.fn()} />);
    expect(screen.getByText('Loading related fields')).toBeInTheDocument();
    unmount();
    const failed = fakeQuery(undefined, { isError: true });
    hooks.useGuideField.mockReturnValue(failed);
    render(<GuideField name={BB} onAddToBuilder={vi.fn()} />);
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(failed.refetch).toHaveBeenCalled();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<GuideField name={BB} onAddToBuilder={vi.fn()} />);
    await expectNoA11yViolations(container);
  });
});
