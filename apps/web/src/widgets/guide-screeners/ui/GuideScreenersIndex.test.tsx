import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { GuideScreenersIndex } from './GuideScreenersIndex';

const hooks = vi.hoisted(() => ({ useGuideIndex: vi.fn(), useGuideScreenerIndex: vi.fn() }));

vi.mock('@/entities/guide', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useGuideIndex: hooks.useGuideIndex,
  useGuideScreenerIndex: hooks.useGuideScreenerIndex,
}));

const section = {
  id: 'screeners',
  title: 'Screeners',
  purpose: 'One page per site screen.',
  entries: 3,
};
const index = {
  what: 'A screener is a saved rule screen.',
  versusEdge: 'An edge is a claim; a screener finds today’s names.',
  count: 3,
  categories: [
    { id: 'breakouts', title: 'Breakouts', purpose: 'Shares leaving a narrow range.', count: 2 },
    { id: 'income', title: 'Option income', purpose: 'Options priced rich.', count: 1 },
  ],
};

beforeEach(() => {
  hooks.useGuideIndex.mockReturnValue(fakeQuery({ sections: [section] }));
  hooks.useGuideScreenerIndex.mockReturnValue(fakeQuery(index));
});

describe('GuideScreenersIndex', () => {
  it('heads the page, says what a screener is and how it differs from an edge', () => {
    render(<GuideScreenersIndex />);
    expect(screen.getByRole('heading', { level: 1, name: 'Screeners' })).toBeInTheDocument();
    expect(screen.getByText('One page per site screen.')).toBeInTheDocument();
    expect(screen.getByText('A screener is a saved rule screen.')).toBeInTheDocument();
    expect(screen.getByText(/An edge is a claim/)).toBeInTheDocument();
  });

  it('shows a card per category in the server’s order, linked, with its count', () => {
    render(<GuideScreenersIndex />);
    const cards = within(screen.getByRole('list', { name: 'The screener categories' }));
    expect(cards.getAllByRole('link').map((l) => [l.textContent, l.getAttribute('href')])).toEqual([
      [expect.stringContaining('Breakouts'), '/guide/screeners/c/breakouts'],
      [expect.stringContaining('Option income'), '/guide/screeners/c/income'],
    ]);
    expect(cards.getByText('Shares leaving a narrow range.')).toBeInTheDocument();
    expect(cards.getByText('2 screeners')).toBeInTheDocument();
    expect(cards.getByText('1 screeners')).toBeInTheDocument();
  });

  it('shows loading, an error with a retry, and no screeners', async () => {
    hooks.useGuideScreenerIndex.mockReturnValue(fakeQuery(undefined));
    const { rerender } = render(<GuideScreenersIndex />);
    expect(screen.getByRole('status')).toBeInTheDocument();
    const failed = fakeQuery(undefined, { isError: true });
    hooks.useGuideScreenerIndex.mockReturnValue(failed);
    rerender(<GuideScreenersIndex />);
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(failed.refetch).toHaveBeenCalled();
    hooks.useGuideScreenerIndex.mockReturnValue(fakeQuery({ ...index, categories: [] }));
    rerender(<GuideScreenersIndex />);
    expect(screen.getByText('The Guide has no screeners.')).toBeInTheDocument();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<GuideScreenersIndex />);
    await expectNoA11yViolations(container);
  });
});
