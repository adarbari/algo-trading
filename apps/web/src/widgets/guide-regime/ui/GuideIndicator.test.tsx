import { render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { GuideIndicator } from './GuideIndicator';

const hooks = vi.hoisted(() => ({ useGuideIndicator: vi.fn() }));

vi.mock('@/entities/guide', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useGuideIndicator: hooks.useGuideIndicator,
}));

const prose = (text: string) => ({ segments: [{ text, field: null }] });

const indicator = {
  key: 'curve_10y3m',
  plainName: 'Is the yield curve inverted?',
  technicalName: '10y minus 3m Treasury spread',
  pace: 'slow',
  summary: prose('Short rates above long ones.'),
  whyItMatters: prose('It has come before every recent recession.'),
  whatOnMeans: prose('The spread is below zero.'),
  leadTime: prose('6 to 24 months.'),
  trackRecord: prose('Few false alarms.'),
  before: [
    { label: '2008', episode: 'gfc_2007', line: prose('Inverted for 16 months before the fall.') },
    { label: '2022', episode: null, line: prose('Inverted, no recession yet.') },
  ],
  how: [
    { text: 'The 10y yield minus the 3m, from ', url: null },
    { text: 'FRED', url: 'https://fred.stlouisfed.org/series/T10Y3M' },
  ],
  feature: 'market.regime_indicators@v1.curve_10y3m',
  sources: [
    { title: 'FRED: 10y minus 3m spread', url: 'https://fred.stlouisfed.org/series/T10Y3M' },
  ],
};

beforeEach(() => {
  hooks.useGuideIndicator.mockReturnValue(fakeQuery(indicator));
});

describe('GuideIndicator', () => {
  it('shows the question, why it matters, when it is on, lead time and track record', async () => {
    const { container } = render(<GuideIndicator indicatorKey="curve_10y3m" />);
    expect(
      screen.getByRole('heading', { level: 1, name: 'Is the yield curve inverted?' }),
    ).toBeVisible();
    expect(screen.getByText('Short rates above long ones.')).toBeVisible();
    expect(screen.getByText(/Slow-moving warning sign · 10y minus 3m/)).toBeVisible();
    expect(screen.getByText('It has come before every recent recession.')).toBeVisible();
    expect(screen.getByText('The spread is below zero.')).toBeVisible();
    const lead = screen.getByRole('region', { name: 'Lead time and track record' });
    expect(lead).toHaveTextContent('6 to 24 months.');
    expect(lead).toHaveTextContent('Few false alarms.');
    await expectNoA11yViolations(container);
  });

  it('links a before-line to its fall’s page, and a line with no fall stays plain', () => {
    render(<GuideIndicator indicatorKey="curve_10y3m" />);
    const before = screen.getByRole('region', { name: 'What it did before' });
    expect(within(before).getByRole('link', { name: '2008' })).toHaveAttribute(
      'href',
      '/guide/regime/episodes/gfc_2007',
    );
    expect(within(before).getByText('2022')).toBeVisible();
    expect(within(before).queryByRole('link', { name: '2022' })).toBeNull();
  });

  it('says how it is computed with its terms linked, the feature it reads and the sources', () => {
    render(<GuideIndicator indicatorKey="curve_10y3m" />);
    const how = screen.getByRole('region', { name: 'How it is computed' });
    expect(within(how).getByRole('link', { name: /^FRED/ })).toHaveAttribute(
      'href',
      'https://fred.stlouisfed.org/series/T10Y3M',
    );
    expect(how).toHaveTextContent('market.regime_indicators@v1.curve_10y3m');
    expect(
      screen.getByRole('link', { name: 'Today’s reading on the Regime page' }),
    ).toHaveAttribute('href', '/regime');
    const sources = screen.getByRole('region', { name: 'Sources' });
    expect(within(sources).getByRole('link', { name: /FRED: 10y minus 3m spread/ })).toBeVisible();
  });

  it('says so for an unknown key, and shows loading and error states', () => {
    hooks.useGuideIndicator.mockReturnValue(fakeQuery(null));
    const { rerender } = render(<GuideIndicator indicatorKey="nope" />);
    expect(screen.getByText('No such indicator')).toBeVisible();
    hooks.useGuideIndicator.mockReturnValue(fakeQuery(undefined));
    rerender(<GuideIndicator indicatorKey="nope" />);
    expect(screen.getByText('Loading the indicator')).toBeVisible();
    hooks.useGuideIndicator.mockReturnValue(fakeQuery(indicator, { isError: true }));
    rerender(<GuideIndicator indicatorKey="nope" />);
    expect(screen.getByText('The indicator failed to load.')).toBeVisible();
  });
});
