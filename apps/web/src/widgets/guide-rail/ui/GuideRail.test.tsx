import { render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { Button } from '@algotrade/ui';

import { expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { GuideRail } from './GuideRail';

const hooks = vi.hoisted(() => ({ useFeatureCatalogue: vi.fn(), useGuideIndex: vi.fn() }));

vi.mock('@/entities/feature', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useFeatureCatalogue: hooks.useFeatureCatalogue,
}));
vi.mock('@/features/guide-search', () => ({
  GuideSearchButton: () => <Button>Search the Guide</Button>,
}));
vi.mock('@/entities/guide', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useGuideIndex: hooks.useGuideIndex,
}));

const field = (name: string, theme: string, reads: string) => ({
  name,
  kind: 'rollup',
  description: reads,
  guide: { theme, reads, uses: [], caveats: [], sources: [] },
});

const names = Array.from({ length: 10 }, (_, i) => `feature.vol_${String(i)}`);
const catalogue = [
  ...names.map((n) => field(n, 'volume', 'How much traded.')),
  field('feature.rsi_14', 'momentum and trend', 'Relative strength, 0 to 100.'),
];

const index = {
  sections: [
    { id: 'start', title: 'Start here', purpose: 'p', entries: 4 },
    { id: 'regime', title: 'Market regime', purpose: 'p', entries: 3 },
    { id: 'playbooks', title: 'Playbooks', purpose: 'p', entries: 3 },
    { id: 'fields', title: 'Fields', purpose: 'p', entries: 11 },
    { id: 'situations', title: 'Situations', purpose: 'p', entries: 2 },
    { id: 'glossary', title: 'Glossary', purpose: 'p', entries: 28 },
  ],
  startPages: [
    { id: 'how_the_app_thinks', order: 1, title: 'How the app thinks about a day', summary: 's' },
    { id: 'read_a_result', order: 2, title: 'Read a screen result', summary: 's' },
  ],
  families: [
    {
      id: 'breakouts',
      title: 'Breakouts',
      playbooks: [
        { id: 'range_breakout', name: 'Range breakout' },
        { id: 'breakout', name: 'Breakout' },
      ],
    },
    { id: 'income', title: 'Option income', playbooks: [{ id: 'vrp_scanner', name: 'VRP' }] },
  ],
  situations: [
    { name: 'Pending takeover', fields: 12, slug: 'pending-takeover' },
    { name: 'Earnings gap', fields: 1, slug: 'earnings-gap' },
  ],
  themeGroups: [
    {
      id: 'chart',
      title: 'The chart',
      themes: [
        { theme: 'momentum and trend', fields: 1 },
        { theme: 'volume', fields: 10 },
      ],
    },
  ],
  intents: [],
  indicators: [
    { key: 'curve_10y3m', plainName: 'Is the yield curve inverted?', pace: 'slow' },
    { key: 'vix_term', plainName: 'Is fear rising?', pace: 'fast' },
  ],
  episodes: [{ key: 'gfc_2007', name: 'Global financial crisis, 2007-09' }],
};

beforeEach(() => {
  hooks.useFeatureCatalogue.mockReturnValue(fakeQuery(catalogue));
  hooks.useGuideIndex.mockReturnValue(fakeQuery(index));
});

describe('GuideRail', () => {
  it('lists every section with the server’s count, and the themes under Fields', () => {
    render(<GuideRail page="fields" />);
    const nav = screen.getByRole('navigation', { name: 'Guide' });
    expect(within(nav).getByRole('link', { name: /^Fields/ })).toHaveTextContent('Fields11');
    expect(within(nav).getByRole('link', { name: /Momentum and trend/ })).toHaveAttribute(
      'href',
      '/guide/fields?theme=momentum+and+trend',
    );
  });

  it('lists the sections in the server’s order: Start here first, the Glossary last', () => {
    render(<GuideRail page="home" />);
    const nav = screen.getByRole('navigation', { name: 'Guide' });
    const top = within(nav)
      .getAllByRole('link')
      .map((l) => l.textContent)
      .filter((t) =>
        /^(Overview|Start here|Market regime|Playbooks|Fields|Situations|Glossary)/.test(t),
      );
    expect(top).toEqual([
      'Overview',
      'Start here4',
      'Market regime3',
      'Playbooks3',
      'Fields11',
      'Situations2',
      'Glossary28',
    ]);
    expect(within(nav).queryByRole('link', { name: 'Breakout' })).toBeNull();
  });

  it('opens the playbooks in family order, marking the current one', () => {
    render(<GuideRail page="playbook" playbook="breakout" />);
    const nav = screen.getByRole('navigation', { name: 'Guide' });
    expect(
      within(nav)
        .getAllByRole('link')
        .map((l) => l.getAttribute('href'))
        .filter((h) => h?.startsWith('/guide/playbooks/')),
    ).toEqual([
      '/guide/playbooks/range_breakout',
      '/guide/playbooks/breakout',
      '/guide/playbooks/vrp_scanner',
    ]);
    expect(within(nav).getByRole('link', { name: 'Breakout' })).toHaveAttribute(
      'aria-current',
      'page',
    );
  });

  it('opens the indicators then the market falls under Market regime, marking the current one', () => {
    render(<GuideRail page="episode" episode="gfc_2007" />);
    const nav = screen.getByRole('navigation', { name: 'Guide' });
    expect(
      within(nav)
        .getAllByRole('link')
        .map((l) => l.getAttribute('href'))
        .filter((h) => h?.startsWith('/guide/regime/')),
    ).toEqual([
      '/guide/regime/indicators/curve_10y3m',
      '/guide/regime/indicators/vix_term',
      '/guide/regime/episodes/gfc_2007',
    ]);
    expect(
      within(nav).getByRole('link', { name: 'Global financial crisis, 2007-09' }),
    ).toHaveAttribute('aria-current', 'page');
  });

  it('opens the situations, marking the current one', () => {
    render(<GuideRail page="situation" situation="earnings-gap" />);
    const nav = screen.getByRole('navigation', { name: 'Guide' });
    expect(within(nav).getByRole('link', { name: 'Earnings gap' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(within(nav).getByRole('link', { name: 'Pending takeover' })).toHaveAttribute(
      'href',
      '/guide/situations/pending-takeover',
    );
  });

  it('opens the current field’s theme with a few of its fields and "N more"', () => {
    render(<GuideRail page="field" field="feature.vol_1" />);
    const nav = screen.getByRole('navigation', { name: 'Guide' });
    expect(within(nav).getByRole('link', { name: 'feature.vol_1' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(within(nav).queryByRole('link', { name: 'feature.vol_9' })).toBeNull();
    expect(within(nav).getByRole('link', { name: '2 more' })).toBeInTheDocument();
    expect(within(nav).queryByRole('link', { name: 'feature.rsi_14' })).toBeNull();
  });

  it('opens the Start here pages in order, numbered, marking the current one', () => {
    render(<GuideRail page="start_page" startPage="read_a_result" />);
    const nav = screen.getByRole('navigation', { name: 'Guide' });
    expect(
      within(nav)
        .getAllByRole('link')
        .map((l) => l.getAttribute('href'))
        .filter((h) => h?.startsWith('/guide/start/')),
    ).toEqual(['/guide/start/how_the_app_thinks', '/guide/start/read_a_result']);
    expect(within(nav).getByRole('link', { name: '2. Read a screen result' })).toHaveAttribute(
      'aria-current',
      'page',
    );
  });

  it('marks the glossary current on a term page', () => {
    render(<GuideRail page="term" />);
    const nav = screen.getByRole('navigation', { name: 'Guide' });
    expect(within(nav).getByRole('link', { name: /^Glossary/ })).toHaveAttribute(
      'aria-current',
      'page',
    );
  });

  it('has the search button and no field filter of its own', () => {
    render(<GuideRail page="home" />);
    expect(screen.getByRole('button', { name: 'Search the Guide' })).toBeInTheDocument();
    expect(screen.queryByRole('searchbox')).toBeNull();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<GuideRail page="field" field="feature.vol_1" />);
    await expectNoA11yViolations(container);
  });
});
