import { render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { GuideEpisode } from './GuideEpisode';

const hooks = vi.hoisted(() => ({ useGuideEpisode: vi.fn() }));

vi.mock('@/entities/guide', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useGuideEpisode: hooks.useGuideEpisode,
}));

const prose = (text: string) => ({ segments: text ? [{ text, field: null }] : [] });

const detail = {
  episode: {
    key: 'gfc_2007',
    name: 'Global financial crisis, 2007-09',
    kind: 'recession',
    peak: '2007-10-09',
    trough: '2009-03-09',
    recovered: '2013-03-28',
    spxDrawdown: -0.57,
    nasdaqDrawdown: -0.55,
    recession: true,
    nberStart: '2007-12-01',
    nberEnd: '2009-06-01',
    knownFrom: '2009-03-09',
  },
  cause: prose('A housing bust spread through the banks.'),
  notes: prose('The S&P 500 took five years to recover.'),
  indicators: [
    {
      key: 'curve_10y3m',
      plainName: 'Is the yield curve inverted?',
      label: '2008',
      line: prose('Inverted for 16 months before the fall.'),
    },
  ],
};

beforeEach(() => {
  hooks.useGuideEpisode.mockReturnValue(fakeQuery(detail));
});

describe('GuideEpisode', () => {
  it('shows the name, cause, facts, notes and the indicators that read it', async () => {
    const { container } = render(<GuideEpisode slug="gfc_2007" />);
    expect(
      screen.getByRole('heading', { level: 1, name: 'Global financial crisis, 2007-09' }),
    ).toBeVisible();
    expect(screen.getByText('Recession bear market')).toBeVisible();
    expect(screen.getByText('A housing bust spread through the banks.')).toBeVisible();
    const facts = screen.getByRole('region', { name: 'The fall' });
    expect(within(facts).getByText('S&P 500 fall').closest('div')).toHaveTextContent(/[-−]57%/);
    expect(within(facts).getByText('Nasdaq fall').closest('div')).toHaveTextContent(/[-−]55%/);
    expect(screen.getByText('The S&P 500 took five years to recover.')).toBeVisible();
    const before = screen.getByRole('region', { name: 'What the warning signs did before it' });
    expect(
      within(before).getByRole('link', { name: 'Is the yield curve inverted?' }),
    ).toHaveAttribute('href', '/guide/regime/indicators/curve_10y3m');
    await expectNoA11yViolations(container);
  });

  it('leaves out empty notes and says a fall has not recovered', () => {
    hooks.useGuideEpisode.mockReturnValue(
      fakeQuery({
        ...detail,
        notes: prose(''),
        episode: { ...detail.episode, recovered: null },
      }),
    );
    render(<GuideEpisode slug="gfc_2007" />);
    expect(screen.queryByRole('region', { name: 'Notes' })).toBeNull();
    expect(screen.getByText('Recovered').closest('div')).toHaveTextContent('Not yet');
  });

  it('says so for an unknown slug, and shows loading and error states', () => {
    hooks.useGuideEpisode.mockReturnValue(fakeQuery(null));
    const { rerender } = render(<GuideEpisode slug="nope" />);
    expect(screen.getByText('No such market fall')).toBeVisible();
    hooks.useGuideEpisode.mockReturnValue(fakeQuery(undefined));
    rerender(<GuideEpisode slug="nope" />);
    expect(screen.getByText('Loading the market fall')).toBeVisible();
    hooks.useGuideEpisode.mockReturnValue(fakeQuery(detail, { isError: true }));
    rerender(<GuideEpisode slug="nope" />);
    expect(screen.getByText('The market fall failed to load.')).toBeVisible();
  });
});
