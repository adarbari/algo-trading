import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { GuideRail } from './GuideRail';

const hooks = vi.hoisted(() => ({ useFeatureCatalogue: vi.fn(), useGuideIndex: vi.fn() }));

vi.mock('@/entities/feature', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useFeatureCatalogue: hooks.useFeatureCatalogue,
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
    { id: 'fields', title: 'Fields', purpose: 'p', entries: 11 },
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
};

beforeEach(() => {
  hooks.useFeatureCatalogue.mockReturnValue(fakeQuery(catalogue));
  hooks.useGuideIndex.mockReturnValue(fakeQuery(index));
});

describe('GuideRail', () => {
  it('lists only the sections that have pages, with the server’s count, and the themes under Fields', () => {
    render(<GuideRail page="fields" />);
    const nav = screen.getByRole('navigation', { name: 'Guide' });
    expect(within(nav).queryByText('Start here')).toBeNull();
    expect(within(nav).getByRole('link', { name: /^Fields/ })).toHaveTextContent('Fields11');
    expect(within(nav).getByRole('link', { name: /Momentum and trend/ })).toHaveAttribute(
      'href',
      '/guide/fields?theme=momentum+and+trend',
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

  it('filters the fields in the browser while a query is typed', async () => {
    const user = userEvent.setup();
    render(<GuideRail page="home" />);
    await user.type(screen.getByRole('searchbox', { name: 'Search the guide' }), 'strength');
    const results = screen.getByRole('navigation', { name: 'Search results' });
    expect(
      within(results)
        .getAllByRole('link')
        .map((l) => l.textContent),
    ).toEqual(['feature.rsi_14']);
    expect(screen.getByText('1 field')).toBeInTheDocument();
    await user.clear(screen.getByRole('searchbox'));
    expect(screen.getByRole('navigation', { name: 'Guide' })).toBeInTheDocument();
  });

  it('says when nothing matches', async () => {
    const user = userEvent.setup();
    render(<GuideRail page="home" />);
    await user.type(screen.getByRole('searchbox'), 'zzzz');
    expect(screen.getByText('No field matches “zzzz”.')).toBeInTheDocument();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<GuideRail page="field" field="feature.vol_1" />);
    await expectNoA11yViolations(container);
  });
});
