import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { GuideScreenerCategory } from './GuideScreenerCategory';

const hooks = vi.hoisted(() => ({ useGuideScreenerCategory: vi.fn() }));

vi.mock('@/entities/guide', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useGuideScreenerCategory: hooks.useGuideScreenerCategory,
}));

const category = {
  id: 'breakouts',
  title: 'Breakouts',
  purpose: 'Shares that leave a narrow range.',
  intro: 'A breakout is a close above a ceiling.',
  screeners: [
    {
      id: 'breakout',
      name: 'Breakout',
      line: 'Closed above the one-month high on volume.',
      edges: [{ id: 'range_edge', name: 'Range edge', status: 'candidate' }],
    },
    { id: 'failed_breakout', name: 'Failed breakout', line: '', edges: [] },
  ],
};

beforeEach(() => {
  hooks.useGuideScreenerCategory.mockReturnValue(fakeQuery(category));
});

describe('GuideScreenerCategory', () => {
  it('heads the page with the family, its purpose and its intro, and links back up', () => {
    render(<GuideScreenerCategory id="breakouts" />);
    expect(screen.getByRole('heading', { level: 1, name: 'Breakouts' })).toBeInTheDocument();
    expect(screen.getByText('Shares that leave a narrow range.')).toBeInTheDocument();
    expect(screen.getByText('A breakout is a close above a ceiling.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Screeners' })).toHaveAttribute(
      'href',
      '/guide/screeners',
    );
  });

  it('lists each screener linked with what it asks and the edges that use it', () => {
    render(<GuideScreenerCategory id="breakouts" />);
    const rows = within(screen.getByRole('list', { name: 'Screeners' }));
    expect(rows.getByRole('link', { name: 'Breakout' })).toHaveAttribute(
      'href',
      '/guide/screeners/breakout',
    );
    expect(rows.getByText('Closed above the one-month high on volume.')).toBeInTheDocument();
    expect(rows.getByRole('link', { name: 'Range edge' })).toHaveAttribute(
      'href',
      '/guide/edges/range_edge',
    );
    expect(rows.getByText('Candidate')).toBeInTheDocument();
    // A screener with no line and no edge is its name alone.
    expect(rows.getByRole('link', { name: 'Failed breakout' })).toBeInTheDocument();
    expect(rows.getAllByText('Used by')).toHaveLength(1);
  });

  it('shows loading, an error with a retry and an unknown category', async () => {
    hooks.useGuideScreenerCategory.mockReturnValue(fakeQuery(undefined));
    const { rerender } = render(<GuideScreenerCategory id="breakouts" />);
    expect(screen.getByRole('status')).toBeInTheDocument();
    const failed = fakeQuery(undefined, { isError: true });
    hooks.useGuideScreenerCategory.mockReturnValue(failed);
    rerender(<GuideScreenerCategory id="breakouts" />);
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(failed.refetch).toHaveBeenCalled();
    hooks.useGuideScreenerCategory.mockReturnValue(fakeQuery(null));
    rerender(<GuideScreenerCategory id="nope" />);
    expect(screen.getByText('No such category')).toBeInTheDocument();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<GuideScreenerCategory id="breakouts" />);
    await expectNoA11yViolations(container);
  });
});
