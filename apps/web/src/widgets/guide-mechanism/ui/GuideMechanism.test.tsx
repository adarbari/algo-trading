import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { Text } from '@algotrade/ui';

import { expectNoA11yViolations, fakeQuery, mechanism } from '@/shared/lib/testing';

import { GuideMechanism, MechanismOutline } from './GuideMechanism';

const hooks = vi.hoisted(() => ({ useGuideMechanism: vi.fn() }));

vi.mock('@/entities/guide', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useGuideMechanism: hooks.useGuideMechanism,
  RelatedTerms: ({ ids }: { ids: string[] }) => <Text>{`related ${ids.join(' ')}`}</Text>,
}));
vi.mock('@/features/guide-help', async () => {
  const { Text } = await import('@algotrade/ui');
  return { termHelp: (id: string) => <Text>{`help ${id}`}</Text> };
});

beforeEach(() => {
  hooks.useGuideMechanism.mockReturnValue(fakeQuery(mechanism()));
});

describe('GuideMechanism', () => {
  it('heads the page with the question, the title and the one-line hero', () => {
    render(<GuideMechanism id="slow_to_update" />);
    expect(screen.getByRole('heading', { level: 1, name: 'Slow to update' })).toBeInTheDocument();
    expect(screen.getByText('Who is slow to update?')).toBeInTheDocument();
    expect(screen.getByText('Prices absorb news in steps, not at once.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Edges' })).toHaveAttribute('href', '/guide/edges');
  });

  it('shows how it works and why it survives, in the order of the file', () => {
    render(<GuideMechanism id="slow_to_update" />);
    expect(screen.getByText(/A company reports and the price moves/)).toBeInTheDocument();
    const survives = screen.getByRole('list', { name: 'Why it survives' });
    expect(
      within(survives)
        .getAllByRole('listitem')
        .map((li) => li.textContent),
    ).toEqual(['Arbitrage is expensive to run.', 'The behaviour is old.']);
  });

  it('shows the stat tiles, citing a source by its number', () => {
    render(<GuideMechanism id="slow_to_update" />);
    const stats = screen.getByRole('region', { name: 'Research figures' });
    expect(within(stats).getByText('t > 3')).toBeInTheDocument();
    expect(within(stats).getByRole('link', { name: '[1]' })).toHaveAttribute('href', '#s1');
    const sources = screen.getByRole('list', { name: 'Sources and further reading' });
    expect(within(sources).getAllByRole('listitem')[0]).toHaveAttribute('id', 's1');
    expect(within(sources).getByRole('link', { name: /McLean and Pontiff/ })).toHaveAttribute(
      'href',
      'https://example.org/mclean',
    );
  });

  it('shows real against decoy and the one thing not to read into it', () => {
    render(<GuideMechanism id="slow_to_update" />);
    expect(screen.getByText('A real edge beats plain momentum.')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Do not read a momentum win rate');
  });

  it('lists its edges linked to their pages, then the ideas not built, closed until opened', async () => {
    render(<GuideMechanism id="slow_to_update" />);
    const edges = screen.getByRole('region', { name: 'The edges in this mechanism' });
    expect(within(edges).getByRole('link', { name: 'Earnings-date advances' })).toHaveAttribute(
      'href',
      '/guide/edges/earnings_date_advance',
    );
    expect(within(edges).getByText('Candidate')).toBeInTheDocument();
    expect(
      within(edges).getByRole('link', { name: 'Live results on the Edges page' }),
    ).toHaveAttribute('href', '/edges');
    expect(screen.queryByRole('region', { name: 'Researched, not built' })).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: /Researched, not built/ }));
    const ideas = screen.getByRole('region', { name: 'Researched, not built' });
    expect(within(ideas).getByText('Year-on-year change in filing text')).toBeInTheDocument();
  });

  it('leaves out the ideas section when none is not built, and says when no edge rests on it', () => {
    hooks.useGuideMechanism.mockReturnValue(fakeQuery(mechanism({ notBuilt: [], edges: [] })));
    render(<GuideMechanism id="slow_to_update" />);
    expect(screen.queryByRole('region', { name: 'Researched, not built' })).toBeNull();
    expect(screen.getByText('No edge rests on this mechanism yet.')).toBeInTheDocument();
  });

  it('filters its edges by status, asset, side and holding when there is a choice', async () => {
    const [first] = mechanism().edges;
    const edges = [
      {
        ...first,
        id: 'a',
        name: 'Alpha edge',
        status: 'candidate',
        asset: 'stocks',
        assetText: 'Stocks',
      },
      {
        ...first,
        id: 'b',
        name: 'Beta edge',
        status: 'rejected',
        asset: 'etfs',
        assetText: 'ETFs',
      },
    ];
    hooks.useGuideMechanism.mockReturnValue(fakeQuery(mechanism({ edges })));
    render(<GuideMechanism id="slow_to_update" />);
    await userEvent.click(screen.getByRole('button', { name: /Status/ }));
    await userEvent.click(await screen.findByRole('button', { name: /Rejected · 1/ }));
    expect(screen.queryByRole('link', { name: 'Alpha edge' })).toBeNull();
    expect(screen.getByRole('link', { name: 'Beta edge' })).toBeVisible();
    await userEvent.click(screen.getByRole('button', { name: 'Clear filters' }));
    expect(screen.getByRole('link', { name: 'Alpha edge' })).toBeVisible();
  });

  it('sends the reader on to the glossary terms it names', () => {
    render(<GuideMechanism id="slow_to_update" />);
    expect(screen.getByText('related edge_how_sure')).toBeInTheDocument();
  });

  it('lists its sections in "On this page"', () => {
    render(<MechanismOutline />);
    const nav = screen.getByRole('navigation', { name: 'On this page' });
    expect(within(nav).getByRole('link', { name: 'Why it survives' })).toHaveAttribute(
      'href',
      '#survives',
    );
  });

  it('shows loading, an error with a retry, and an unknown mechanism', async () => {
    hooks.useGuideMechanism.mockReturnValue(fakeQuery(undefined));
    const { rerender } = render(<GuideMechanism id="x" />);
    expect(screen.getByRole('status')).toBeInTheDocument();
    const failed = fakeQuery(undefined, { isError: true });
    hooks.useGuideMechanism.mockReturnValue(failed);
    rerender(<GuideMechanism id="x" />);
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(failed.refetch).toHaveBeenCalled();
    hooks.useGuideMechanism.mockReturnValue(fakeQuery(null));
    rerender(<GuideMechanism id="nope" />);
    expect(screen.getByText('No such mechanism')).toBeInTheDocument();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<GuideMechanism id="slow_to_update" />);
    await expectNoA11yViolations(container);
  });
});
