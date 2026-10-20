import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { GuideScreener } from './GuideScreener';

const hooks = vi.hoisted(() => ({ useGuideScreener: vi.fn(), useGuideScreenerEdges: vi.fn() }));

vi.mock('@/entities/guide', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useGuideScreener: hooks.useGuideScreener,
  useGuideScreenerEdges: hooks.useGuideScreenerEdges,
}));

vi.mock('@/features/guide-help', async () => {
  const { Text } = await import('@algotrade/ui');
  return { termHelp: (id: string) => <Text>{`help ${id}`}</Text> };
});

stubElementSize();

const plain = (text: string) => ({ segments: [{ text }] });
const volume = 'feature.rel_volume';

const screener = {
  id: 'breakout',
  name: 'Breakout',
  family: 'breakouts',
  familyTitle: 'Breakouts',
  version: 1,
  prose: {
    summary: {
      segments: [
        { text: 'Finds shares that closed above their one-month high.' },
        { text: '[^1]', source: 1 },
      ],
    },
    hit: plain('A close above the prior 20-session high.'),
    notChecked: {
      segments: [{ text: 'Whether the break holds, or the market regime.' }],
    },
    beforeActing: [
      {
        segments: [
          { text: 'Earnings days run 3 to 10 times normal volume; read ' },
          { text: volume, field: volume },
          { text: ' with care.' },
        ],
      },
    ],
    sources: [
      { title: 'O’Neil, How to Make Money in Stocks', url: null, note: 'The breakout setup.' },
      {
        title: 'Faber, Tactical Asset Allocation (2007)',
        url: 'https://example.org/f',
        note: 'Trend.',
      },
    ],
  },
  criteria: [
    {
      name: 'breakout_20d',
      asks: 'Closed above the 20-session high',
      field: 'feature.breakout_magnitude_20d',
      rule: 'gt 0',
      mode: 'hard',
      onMiss: null,
    },
    {
      name: 'not_extended',
      asks: null,
      field: 'feature.stretch_sma20_atr',
      rule: 'lte 3 soft tolerance 1.0',
      mode: 'soft',
      onMiss: 'WATCH',
    },
  ],
  tieBreak: 'feature.breakout_magnitude_20d',
  tieBreakDescending: true,
  related: [
    { id: 'failed_breakout', name: 'Failed breakout', reason: 'the same break after it fails' },
  ],
  situations: [{ slug: 'earnings-gap', name: 'Earnings gap inside the window', fields: [volume] }],
};

const implemented = [
  {
    id: 'range_breakout_edge',
    name: 'Range breakouts',
    thesis: 'Shares closing above a one-month high keep rising for a few weeks.',
    status: 'candidate',
  },
];

function setup() {
  const onSeeHits = vi.fn();
  const onOpenBuilder = vi.fn();
  const view = render(
    <GuideScreener id="breakout" onSeeHits={onSeeHits} onOpenBuilder={onOpenBuilder} />,
  );
  return { onSeeHits, onOpenBuilder, ...view };
}

beforeEach(() => {
  hooks.useGuideScreener.mockReturnValue(fakeQuery(screener));
  hooks.useGuideScreenerEdges.mockReturnValue(fakeQuery(implemented));
});

describe('GuideScreener', () => {
  it('heads the page with the preset id and version, the name and the summary as the hero', () => {
    setup();
    expect(screen.getByText('site preset · breakout v1 · Breakouts')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1, name: 'Breakout' })).toBeInTheDocument();
    expect(
      screen.getByText('Finds shares that closed above their one-month high.'),
    ).toBeInTheDocument();
  });

  it('opens today’s hits and the Builder from the two buttons', async () => {
    const { onSeeHits, onOpenBuilder } = setup();
    await userEvent.click(screen.getByRole('button', { name: 'See today’s hits' }));
    expect(onSeeHits).toHaveBeenCalledOnce();
    await userEvent.click(screen.getByRole('button', { name: 'Open in Builder' }));
    expect(onOpenBuilder).toHaveBeenCalledOnce();
  });

  it('shows what a hit looks like beside what it does not check', () => {
    setup();
    expect(
      within(screen.getByRole('region', { name: 'What a hit looks like' })).getByText(
        'A close above the prior 20-session high.',
      ),
    ).toBeInTheDocument();
    expect(screen.getByText('What it does not check')).toBeInTheDocument();
    expect(screen.getByText(/Whether the break holds/)).toBeInTheDocument();
  });

  it('lists the criteria: what it asks, the field linked, the rule and what a miss does', () => {
    setup();
    const table = within(screen.getByRole('grid', { name: 'Breakout criteria' }));
    const first = within(table.getByRole('row', { name: /Closed above the 20-session high/ }));
    expect(first.getByRole('link', { name: 'feature.breakout_magnitude_20d' })).toHaveAttribute(
      'href',
      '/guide/fields/feature.breakout_magnitude_20d',
    );
    expect(first.getByText('gt 0')).toBeInTheDocument();
    expect(first.getByText('reject')).toBeInTheDocument();
    const soft = within(table.getByRole('row', { name: /not_extended/ }));
    expect(soft.getByText('lte 3 soft tolerance 1.0')).toBeInTheDocument();
    expect(soft.getByText('WATCH')).toBeInTheDocument();
    expect(
      screen.getByText('Ranked by feature.breakout_magnitude_20d, highest first.'),
    ).toBeInTheDocument();
  });

  it('links the fields in the caveats and the situations that fool its fields', () => {
    setup();
    const before = screen.getByRole('region', { name: 'Before you act on a hit' });
    expect(within(before).getByRole('link', { name: volume })).toHaveAttribute(
      'href',
      `/guide/fields/${encodeURIComponent(volume)}`,
    );
    expect(
      within(before).getByRole('link', { name: 'Earnings gap inside the window' }),
    ).toHaveAttribute('href', '/guide/situations/earnings-gap');
  });

  it('lists the edges it implements, each linked to its Guide page with its status', () => {
    setup();
    const edges = screen.getByRole('region', { name: 'Edges it implements' });
    expect(within(edges).getByRole('link', { name: 'Range breakouts' })).toHaveAttribute(
      'href',
      '/guide/edges/range_breakout_edge',
    );
    expect(within(edges).getByText('Candidate')).toBeInTheDocument();
    expect(within(edges).getByText(/keep rising for a few weeks/)).toBeInTheDocument();
  });

  it('shows no edges panel for a screener no edge uses', () => {
    hooks.useGuideScreenerEdges.mockReturnValue(fakeQuery([]));
    setup();
    expect(screen.queryByRole('region', { name: 'Edges it implements' })).toBeNull();
  });

  it('links related screeners with their reasons, and lists the sources', () => {
    setup();
    const related = screen.getByRole('region', { name: 'Related screeners' });
    expect(within(related).getByRole('link', { name: 'Failed breakout' })).toHaveAttribute(
      'href',
      '/guide/screeners/failed_breakout',
    );
    expect(within(related).getByText(/the same break after it fails/)).toBeInTheDocument();
    const sources = within(screen.getByRole('region', { name: 'Sources' }));
    // A source with no verified page is plain text; one with a page is a link.
    expect(sources.getByText('O’Neil, How to Make Money in Stocks')).toBeInTheDocument();
    expect(sources.getByRole('link', { name: /Faber/ })).toHaveAttribute(
      'href',
      'https://example.org/f',
    );
  });

  it('links the prose marker to its source and the page up to its section and category', () => {
    setup();
    expect(screen.getByRole('link', { name: '[1]' })).toHaveAttribute('href', '#s1');
    expect(screen.getByRole('link', { name: 'Screeners' })).toHaveAttribute(
      'href',
      '/guide/screeners',
    );
    expect(screen.getByRole('link', { name: 'Breakouts' })).toHaveAttribute(
      'href',
      '/guide/screeners/c/breakouts',
    );
  });

  it('shows the criteria alone when no prose is written for the preset', () => {
    hooks.useGuideScreener.mockReturnValue(
      fakeQuery({ ...screener, prose: null, related: [], situations: [] }),
    );
    setup();
    expect(screen.getByText(/No screener prose is written/)).toBeInTheDocument();
    expect(screen.getByRole('grid', { name: 'Breakout criteria' })).toBeInTheDocument();
    expect(screen.queryByText('What it does not check')).toBeNull();
    expect(screen.queryByRole('region', { name: 'Before you act on a hit' })).toBeNull();
  });

  it('shows loading, an error with a retry, and an unknown screener', async () => {
    hooks.useGuideScreener.mockReturnValue(fakeQuery(undefined));
    const { rerender } = setup();
    expect(screen.getByRole('status')).toBeInTheDocument();
    const failed = fakeQuery(undefined, { isError: true });
    hooks.useGuideScreener.mockReturnValue(failed);
    rerender(<GuideScreener id="breakout" onSeeHits={vi.fn()} onOpenBuilder={vi.fn()} />);
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(failed.refetch).toHaveBeenCalled();
    hooks.useGuideScreener.mockReturnValue(fakeQuery(null));
    rerender(<GuideScreener id="nope" onSeeHits={vi.fn()} onOpenBuilder={vi.fn()} />);
    expect(screen.getByText('No such screener')).toBeInTheDocument();
  });

  it('has no accessibility violations', async () => {
    const { container } = setup();
    await expectNoA11yViolations(container);
  });
});
