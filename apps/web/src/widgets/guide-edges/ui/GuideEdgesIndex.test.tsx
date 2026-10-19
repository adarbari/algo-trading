import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { edgeIndex, expectNoA11yViolations, fakeQuery, idea } from '@/shared/lib/testing';

import { GuideEdgesIndex } from './GuideEdgesIndex';

const hooks = vi.hoisted(() => ({ useGuideEdgeIndex: vi.fn(), useGuideIndex: vi.fn() }));

vi.mock('@/entities/guide', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useGuideEdgeIndex: hooks.useGuideEdgeIndex,
  useGuideIndex: hooks.useGuideIndex,
}));
vi.mock('@/features/guide-help', async () => {
  const { Text } = await import('@algotrade/ui');
  return {
    termHelp: (id: string) => <Text>{`help ${id}`}</Text>,
    GuideHelp: ({ entry }: { entry: { id: string } }) => <Text>{`guide ${entry.id}`}</Text>,
  };
});

const section = { id: 'edges', title: 'Edges', purpose: 'Why an edge should work.', entries: 3 };

beforeEach(() => {
  hooks.useGuideEdgeIndex.mockReturnValue(fakeQuery(edgeIndex()));
  hooks.useGuideIndex.mockReturnValue(fakeQuery({ sections: [section] }));
});

describe('GuideEdgesIndex', () => {
  it('heads the page with the section and its purpose, and opens the live Edges page', async () => {
    const onOpenEdgesPage = vi.fn();
    render(<GuideEdgesIndex onOpenEdgesPage={onOpenEdgesPage} />);
    expect(screen.getByRole('heading', { level: 1, name: 'Edges' })).toBeInTheDocument();
    expect(screen.getByText('Why an edge should work.')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Open the Edges page' }));
    expect(onOpenEdgesPage).toHaveBeenCalledOnce();
    expect(screen.getByText('guide read_an_edge_page')).toBeInTheDocument();
  });

  it('shows a card per mechanism: question, link, hero, example and counts by status', () => {
    render(<GuideEdgesIndex onOpenEdgesPage={vi.fn()} />);
    const cards = screen.getByRole('list', { name: 'The mechanisms' });
    const slow = within(cards).getByRole('link', { name: 'Slow to update' });
    expect(slow).toHaveAttribute('href', '/guide/edges/m/slow_to_update');
    expect(within(cards).getByText('Who is slow to update?')).toBeInTheDocument();
    expect(within(cards).getByText(/Prices absorb news in steps/)).toBeInTheDocument();
    expect(within(cards).getByText('e.g. post-earnings drift')).toBeInTheDocument();
    expect(within(cards).getByText('2 edges')).toBeInTheDocument();
    expect(within(cards).getByText('Candidate 2')).toBeInTheDocument();
    expect(within(cards).getByText('Blocked 1')).toBeInTheDocument();
    expect(within(cards).getByText('1 ideas not built')).toBeInTheDocument();
  });

  it('narrows the cards by a search and by the server’s filters, and says when none is left', async () => {
    render(<GuideEdgesIndex onOpenEdgesPage={vi.fn()} />);
    await userEvent.type(screen.getByRole('searchbox', { name: 'Search the edges' }), 'index');
    const cards = screen.getByRole('list', { name: 'The mechanisms' });
    expect(within(cards).queryByRole('link', { name: 'Slow to update' })).toBeNull();
    expect(within(cards).getByRole('link', { name: 'Forced buyers and sellers' })).toBeVisible();
    await userEvent.clear(screen.getByRole('searchbox', { name: 'Search the edges' }));
    await userEvent.type(screen.getByRole('searchbox', { name: 'Search the edges' }), 'zzz');
    expect(screen.getByText('No mechanism matches these filters.')).toBeInTheDocument();
  });

  it('offers the asset filter with the server’s words and counts', async () => {
    render(<GuideEdgesIndex onOpenEdgesPage={vi.fn()} />);
    await userEvent.click(screen.getByRole('button', { name: /Asset/ }));
    await userEvent.click(await screen.findByRole('button', { name: /ETFs and funds · 1/ }));
    const cards = screen.getByRole('list', { name: 'The mechanisms' });
    expect(within(cards).getByRole('link', { name: 'Slow to update' })).toBeVisible();
    expect(within(cards).queryByRole('link', { name: 'Forced buyers and sellers' })).toBeNull();
  });

  it('lists the edges set aside with the reason on file, and the ideas not built with their verdict', () => {
    render(<GuideEdgesIndex onOpenEdgesPage={vi.fn()} />);
    const aside = screen.getByRole('region', { name: 'Checked and set aside' });
    expect(within(aside).getByRole('link', { name: 'Index additions' })).toHaveAttribute(
      'href',
      '/guide/edges/index_adds',
    );
    expect(within(aside).getByText(/index membership history is not licensed/)).toBeVisible();
    expect(within(aside).getByText('help edge_status')).toBeInTheDocument();
    const ideas = screen.getByRole('region', { name: 'Researched, not built' });
    expect(within(ideas).getByText('Dead')).toBeInTheDocument();
    expect(within(ideas).getByText('Gone in large caps since the mid-2000s.')).toBeInTheDocument();
    expect(within(ideas).getByText('help idea_verdict')).toBeInTheDocument();
  });

  it('shows the first ideas and a button for all of them', async () => {
    const many = Array.from({ length: 30 }, (_, i) =>
      idea({ id: `i${String(i)}`, title: `Idea ${String(i)}` }),
    );
    hooks.useGuideEdgeIndex.mockReturnValue(fakeQuery(edgeIndex({ notBuilt: many })));
    render(<GuideEdgesIndex onOpenEdgesPage={vi.fn()} />);
    const list = () => screen.getByRole('list', { name: 'Researched, not built' });
    expect(within(list()).getAllByRole('listitem')).toHaveLength(12);
    await userEvent.click(screen.getByRole('button', { name: 'Show all 30 ideas' }));
    expect(within(list()).getAllByRole('listitem')).toHaveLength(30);
  });

  it('shows loading, an error with a retry, and an empty section', async () => {
    hooks.useGuideEdgeIndex.mockReturnValue(fakeQuery(undefined));
    const { rerender } = render(<GuideEdgesIndex onOpenEdgesPage={vi.fn()} />);
    expect(screen.getByRole('status')).toBeInTheDocument();
    const failed = fakeQuery(undefined, { isError: true });
    hooks.useGuideEdgeIndex.mockReturnValue(failed);
    rerender(<GuideEdgesIndex onOpenEdgesPage={vi.fn()} />);
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(failed.refetch).toHaveBeenCalled();
    hooks.useGuideEdgeIndex.mockReturnValue(fakeQuery(null));
    rerender(<GuideEdgesIndex onOpenEdgesPage={vi.fn()} />);
    expect(screen.getByText('The Guide has no Edges section.')).toBeInTheDocument();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<GuideEdgesIndex onOpenEdgesPage={vi.fn()} />);
    await expectNoA11yViolations(container);
  });
});
