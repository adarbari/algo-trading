import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { GuideHome } from './GuideHome';

const hooks = vi.hoisted(() => ({ useGuideIndex: vi.fn() }));

vi.mock('@/entities/guide', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useGuideIndex: hooks.useGuideIndex,
}));

const index = {
  sections: [
    { id: 'start', title: 'Start here', purpose: 'How the app thinks.', entries: 4 },
    { id: 'regime', title: 'Market regime', purpose: 'The weather.', entries: 20 },
    { id: 'playbooks', title: 'Playbooks', purpose: 'One page per site screen.', entries: 3 },
    { id: 'fields', title: 'Fields', purpose: 'Every catalogue field.', entries: 399 },
    { id: 'situations', title: 'Situations', purpose: 'States that fool fields.', entries: 2 },
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
    { name: 'Earnings gap inside the window', fields: 1, slug: 'earnings-gap' },
  ],
  themeGroups: [
    {
      id: 'tradeable',
      title: 'Who is tradeable',
      themes: [
        { theme: 'instrument gates', fields: 23 },
        { theme: 'liquidity', fields: 15 },
      ],
    },
    { id: 'chart', title: 'The chart', themes: [{ theme: 'volume', fields: 35 }] },
  ],
  intents: [{ intent: 'A squeeze', fields: 3 }],
  indicators: [
    { key: 'curve_10y3m', plainName: 'Is the yield curve inverted?', pace: 'slow' },
    { key: 'vix_term', plainName: 'Is fear rising?', pace: 'fast' },
  ],
  episodes: [{ key: 'gfc_2007', name: 'Global financial crisis, 2007-09' }],
};

beforeEach(() => {
  hooks.useGuideIndex.mockReturnValue(fakeQuery(index));
});

describe('GuideHome', () => {
  it('lists the warning signs and the market falls under Market regime, each a link to its page', () => {
    render(<GuideHome />);
    const regime = screen.getByRole('region', { name: 'Market regime' });
    expect(within(regime).getByRole('link', { name: 'Is fear rising?' })).toHaveAttribute(
      'href',
      '/guide/regime/indicators/vix_term',
    );
    expect(
      within(regime).getByRole('link', { name: 'Global financial crisis, 2007-09' }),
    ).toHaveAttribute('href', '/guide/regime/episodes/gfc_2007');
    expect(
      within(regime).getByRole('link', { name: 'The warning signs and the falls' }),
    ).toHaveAttribute('href', '/guide/regime');
  });

  it('shows only the sections that have pages, in the server’s order, with its purpose', () => {
    render(<GuideHome />);
    expect(screen.getByRole('heading', { level: 1, name: 'Guide' })).toBeInTheDocument();
    expect(screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)).toEqual([
      'Market regime',
      'Playbooks',
      'Fields',
      'Situations',
    ]);
    expect(screen.queryByText('Start here')).toBeNull();
    expect(screen.getByText('Every catalogue field.')).toBeInTheDocument();
    expect(screen.getByText('399 entries')).toBeInTheDocument();
  });

  it('lists the theme groups in the server’s order with their counts, each theme a link', () => {
    render(<GuideHome />);
    const groups = screen.getAllByRole('region').map((r) => r.getAttribute('aria-label'));
    expect(groups).toContain('Who is tradeable');
    expect(groups.indexOf('The chart')).toBeGreaterThan(groups.indexOf('Who is tradeable'));
    const tradeable = screen.getByRole('region', { name: 'Who is tradeable' });
    expect(within(tradeable).getByRole('link', { name: 'Instrument gates · 23' })).toHaveAttribute(
      'href',
      '/guide/fields?theme=instrument+gates',
    );
    expect(screen.getByRole('link', { name: 'By intent' })).toHaveAttribute(
      'href',
      '/guide/fields?view=intent',
    );
    expect(screen.getByRole('link', { name: 'A to Z' })).toHaveAttribute(
      'href',
      '/guide/fields?view=az',
    );
  });

  it('lists the playbook families with each playbook linked to its page', () => {
    render(<GuideHome />);
    const family = screen.getByRole('region', { name: 'Breakouts' });
    expect(within(family).getByRole('link', { name: 'Range breakout' })).toHaveAttribute(
      'href',
      '/guide/playbooks/range_breakout',
    );
    expect(screen.getByRole('link', { name: 'What each one says' })).toHaveAttribute(
      'href',
      '/guide/playbooks',
    );
  });

  it('lists the situations with how many fields each fools, each linked to its page', () => {
    render(<GuideHome />);
    expect(screen.getByRole('link', { name: 'Pending takeover · 12' })).toHaveAttribute(
      'href',
      '/guide/situations/pending-takeover',
    );
  });

  it('shows loading, an error with a retry, and an empty guide', async () => {
    hooks.useGuideIndex.mockReturnValue(fakeQuery(undefined));
    const { rerender } = render(<GuideHome />);
    expect(screen.getByRole('status')).toBeInTheDocument();
    const failed = fakeQuery(undefined, { isError: true });
    hooks.useGuideIndex.mockReturnValue(failed);
    rerender(<GuideHome />);
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(failed.refetch).toHaveBeenCalled();
    hooks.useGuideIndex.mockReturnValue(fakeQuery(null));
    rerender(<GuideHome />);
    expect(screen.getByText('The Guide has no entries.')).toBeInTheDocument();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<GuideHome />);
    await expectNoA11yViolations(container);
  });
});
