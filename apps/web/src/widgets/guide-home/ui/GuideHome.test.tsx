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
    { id: 'fields', title: 'Fields', purpose: 'Every catalogue field.', entries: 399 },
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
};

beforeEach(() => {
  hooks.useGuideIndex.mockReturnValue(fakeQuery(index));
});

describe('GuideHome', () => {
  it('shows only the sections that have pages, with the server’s purpose', () => {
    render(<GuideHome />);
    expect(screen.getByRole('heading', { level: 1, name: 'Guide' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 2, name: 'Fields' })).toBeInTheDocument();
    expect(screen.queryByText('Start here')).toBeNull();
    expect(screen.queryByText('Market regime')).toBeNull();
    expect(screen.getByText('Every catalogue field.')).toBeInTheDocument();
    expect(screen.getByText('399 entries')).toBeInTheDocument();
  });

  it('lists the theme groups in the server’s order with their counts, each theme a link', () => {
    render(<GuideHome />);
    const groups = screen.getAllByRole('region').map((r) => r.getAttribute('aria-label'));
    expect(groups).toEqual(['Fields', 'Who is tradeable', 'The chart']);
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
