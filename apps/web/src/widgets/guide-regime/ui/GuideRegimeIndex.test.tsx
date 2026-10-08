import { render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { GuideRegimeIndex } from './GuideRegimeIndex';

const hooks = vi.hoisted(() => ({ useGuideIndex: vi.fn() }));

vi.mock('@/entities/guide', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useGuideIndex: hooks.useGuideIndex,
}));

const index = {
  sections: [{ id: 'regime', title: 'Market regime', purpose: 'The weather.', entries: 4 }],
  indicators: [
    { key: 'curve_10y3m', plainName: 'Is the yield curve inverted?', pace: 'slow' },
    { key: 'hy_oas', plainName: 'Are credit spreads widening?', pace: 'slow' },
    { key: 'vix_term', plainName: 'Is fear rising?', pace: 'fast' },
  ],
  episodes: [{ key: 'gfc_2007', name: 'Global financial crisis, 2007-09' }],
};

beforeEach(() => {
  hooks.useGuideIndex.mockReturnValue(fakeQuery(index));
});

describe('GuideRegimeIndex', () => {
  it('lists the slow warning signs, then the fast ones, then the falls, each a link', async () => {
    const { container } = render(<GuideRegimeIndex />);
    expect(screen.getByRole('heading', { level: 1, name: 'Market regime' })).toBeVisible();
    expect(screen.getByText('The weather.')).toBeVisible();
    const slow = screen.getByRole('region', { name: 'Slow-moving warning signs' });
    expect(
      within(slow)
        .getAllByRole('link')
        .map((l) => l.getAttribute('href')),
    ).toEqual(['/guide/regime/indicators/curve_10y3m', '/guide/regime/indicators/hy_oas']);
    const fast = screen.getByRole('region', { name: 'Fast-moving market signs' });
    expect(within(fast).getByRole('link', { name: 'Is fear rising?' })).toBeVisible();
    const falls = screen.getByRole('region', { name: 'Market falls' });
    expect(within(falls).getByRole('link', { name: /Global financial crisis/ })).toHaveAttribute(
      'href',
      '/guide/regime/episodes/gfc_2007',
    );
    await expectNoA11yViolations(container);
  });

  it('links to today’s readings on the Regime page', () => {
    render(<GuideRegimeIndex />);
    expect(
      screen.getByRole('link', { name: 'Today’s readings on the Regime page' }),
    ).toHaveAttribute('href', '/regime');
  });

  it('shows a skeleton while loading, a retry on error, and an empty state without entries', () => {
    hooks.useGuideIndex.mockReturnValue(fakeQuery(undefined));
    const { rerender } = render(<GuideRegimeIndex />);
    expect(screen.getByText('Loading market regime')).toBeVisible();
    hooks.useGuideIndex.mockReturnValue(fakeQuery(index, { isError: true }));
    rerender(<GuideRegimeIndex />);
    expect(screen.getByText('The Guide failed to load.')).toBeVisible();
    hooks.useGuideIndex.mockReturnValue(fakeQuery({ ...index, indicators: [], episodes: [] }));
    rerender(<GuideRegimeIndex />);
    expect(screen.getByText('The Guide has no market regime entries.')).toBeVisible();
  });
});
