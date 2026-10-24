import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { filterSearch } from '@/features/filter-bar';

import { EDGE_ROWS_FIXTURE, EDGES_FIXTURE } from '@/entities/edge';
import { gql, TestQueryProvider } from '@/shared/api';
import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { EdgeList, type EdgeListSearch } from './EdgeList';

vi.mock('@/shared/api', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  gql: vi.fn(),
}));

const hooks = vi.hoisted(() => ({
  useEdges: vi.fn(),
  useEdgeProblems: vi.fn(),
  useEdgeLiveStates: vi.fn(),
}));
vi.mock('@/entities/edge', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useEdges: hooks.useEdges,
  useEdgeProblems: hooks.useEdgeProblems,
  useEdgeLiveStates: hooks.useEdgeLiveStates,
}));
vi.mock('@/features/guide-help', async () => {
  const { Text } = await import('@algotrade/ui');
  return {
    GuideHelp: ({ entry }: { entry: { id: string } }) => <Text>{`help ${entry.id}`}</Text>,
    termHelp: (id: string) => <Text>{`help ${id}`}</Text>,
  };
});

stubElementSize();

const FILTER_SET = {
  filterSet: {
    surface: 'edges',
    label: 'Edges',
    filters: [
      {
        id: 'status',
        label: 'Status',
        group: 'SETUP',
        kind: 'PICK',
        guide: 'term:filter_edge_status',
        options: [
          { value: 'candidate', label: 'Candidate' },
          { value: 'rejected', label: 'Rejected' },
        ],
        bins: [],
        windowUnit: null,
      },
      {
        id: 'mine',
        label: 'Mine',
        group: 'SETUP',
        kind: 'TOGGLE',
        guide: 'term:filter_edge_mine',
        options: [],
        bins: [],
        windowUnit: null,
      },
    ],
  },
};

/** The page's job: the search params held in state, a patch applied to them. */
function Held({
  initial = {},
  onPatch,
}: {
  initial?: EdgeListSearch;
  onPatch?: (p: unknown) => void;
}) {
  const [search, setSearch] = useState(initial);
  return (
    <EdgeList
      onSelect={vi.fn()}
      search={search}
      onSearchChange={(patch) => {
        onPatch?.(patch);
        setSearch((previous) => {
          const next = Object.fromEntries(
            Object.entries({ ...previous, ...patch }).filter(([, v]) => v !== undefined),
          );
          return {
            ...filterSearch(next),
            ...(typeof next['q'] === 'string' ? { q: next['q'] } : {}),
          };
        });
      }}
    />
  );
}

const setup = (initial: EdgeListSearch = {}, onPatch?: (p: unknown) => void) =>
  render(
    <TestQueryProvider>
      <Held initial={initial} {...(onPatch ? { onPatch } : {})} />
    </TestQueryProvider>,
  );

/** What the list read for the last call: its filters and search text. */
const lastRead = () => hooks.useEdges.mock.calls.at(-1) as [{ id: string }[], string];

beforeEach(() => {
  hooks.useEdges.mockReset();
  hooks.useEdges.mockReturnValue(fakeQuery(EDGE_ROWS_FIXTURE));
  hooks.useEdgeProblems.mockReturnValue(fakeQuery(EDGES_FIXTURE.edgeProblems));
  vi.mocked(gql).mockResolvedValue(FILTER_SET);
  hooks.useEdgeLiveStates.mockReturnValue(
    fakeQuery([
      {
        edgeId: 'earnings_drift',
        name: 'Earnings drift',
        state: 'below',
        closed: 20,
        winRate: 0.2,
        headline: '4 of 20 closed trades won.',
        followed: false,
      },
    ]),
  );
});

describe('EdgeList', () => {
  it('groups the edges by verdict, best first, each with its screens, result and trades', async () => {
    const { container } = setup();
    const table = screen.getByRole('grid', { name: 'Edges' });
    const headings = within(table)
      .getAllByRole('rowheader')
      .map((h) => h.textContent);
    expect(headings).toEqual(['Promising · 1', 'Not working · 1', 'Waiting on data · 2']);
    const momentum = within(table).getByRole('row', { name: /Momentum 12-1/ });
    expect(within(momentum).getByText('screen: momentum_12_1 · site edge')).toBeInTheDocument();
    expect(within(momentum).getByText('Win rate 57% · base rate 52%')).toBeInTheDocument();
    expect(within(momentum).getByText('70')).toBeInTheDocument();
    expect(within(momentum).getByText('Candidate')).toBeInTheDocument();
    const drift = within(table).getByRole('row', { name: /Earnings drift/ });
    expect(within(drift).getByText('screens: pead, pead_volume · site edge')).toBeInTheDocument();
    expect(within(drift).getByText('Below range')).toBeInTheDocument(); // its live state
    expect(within(momentum).queryByText('Below range')).not.toBeInTheDocument(); // none recorded
    const waiting = within(table).getByRole('row', { name: /S&P 500 index changes/ });
    expect(within(waiting).getByText('no screen yet · site edge')).toBeInTheDocument();
    expect(within(waiting).getByText('Rejected')).toBeInTheDocument();
    for (const id of [
      'verdict',
      'live_state',
      'edge_state',
      'trades',
      'out_of_sample',
      'read_an_edge_page',
    ]) {
      expect(screen.getByText(`help ${id}`)).toBeInTheDocument();
    }
    await expectNoA11yViolations(container);
  });

  it('names an edge file that did not load', () => {
    setup();
    expect(screen.getByText("broken.toml extends: no edge 'ghost'")).toBeInTheDocument();
    expect(screen.getByText('help edge_left_out')).toBeInTheDocument();
  });

  it('reads the filters in the URL and the search text, with the filter bar and its count', async () => {
    const onPatch = vi.fn();
    setup({ f: 'mine:' }, onPatch);
    expect(lastRead()[0]).toEqual([expect.objectContaining({ id: 'mine' })]);
    expect(await screen.findByRole('button', { name: /Setup/ })).toBeInTheDocument();
    await userEvent.type(screen.getByRole('searchbox', { name: 'Search edges' }), 'drift');
    expect(onPatch).toHaveBeenLastCalledWith({ q: 'drift' });
    expect(screen.getByRole('searchbox', { name: 'Search edges' })).toHaveValue('drift');
  });

  it('says no edge is declared only when none is, and offers the way back when nothing matches', async () => {
    hooks.useEdges.mockReturnValue(
      fakeQuery({ ...EDGE_ROWS_FIXTURE, items: [], facets: { total: 0, matched: 0, items: [] } }),
    );
    const { unmount } = setup();
    expect(screen.getByText('No edge is declared.')).toBeInTheDocument();
    unmount();
    hooks.useEdges.mockReturnValue(
      fakeQuery({ ...EDGE_ROWS_FIXTURE, items: [], facets: { total: 4, matched: 0, items: [] } }),
    );
    setup({ f: 'status:rejected', q: 'zzz' });
    expect(screen.queryByText('No edge is declared.')).not.toBeInTheDocument();
    expect(await screen.findByText('No edges match this filter')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Clear the search' }));
    expect(screen.getByRole('searchbox', { name: 'Search edges' })).toHaveValue('');
  });

  it('offers to clear the search when the text alone matches nothing', async () => {
    hooks.useEdges.mockReturnValue(
      fakeQuery({ ...EDGE_ROWS_FIXTURE, items: [], facets: { total: 4, matched: 0, items: [] } }),
    );
    setup({ q: 'zzz' });
    expect(screen.getByText('No edge matches "zzz"')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Clear the search' }));
    await vi.waitFor(() => {
      expect(lastRead()[1]).toBe('');
    });
  });

  it('opens an edge on a row click', async () => {
    const onSelect = vi.fn();
    render(<EdgeList onSelect={onSelect} search={{}} onSearchChange={vi.fn()} />, {
      wrapper: TestQueryProvider,
    });
    await userEvent.click(screen.getByRole('row', { name: /Momentum 12-1/ }));
    expect(onSelect).toHaveBeenCalledWith('momentum_12_1');
  });

  it('shows the loading, error and empty states', () => {
    hooks.useEdges.mockReturnValue(fakeQuery(undefined));
    const { rerender } = render(
      <EdgeList onSelect={vi.fn()} search={{}} onSearchChange={vi.fn()} />,
      {
        wrapper: TestQueryProvider,
      },
    );
    expect(screen.getByText('Loading edges…')).toBeInTheDocument();
    hooks.useEdges.mockReturnValue(fakeQuery(undefined, { isError: true }));
    rerender(<EdgeList onSelect={vi.fn()} search={{}} onSearchChange={vi.fn()} />);
    expect(screen.getByText('The edges failed to load.')).toBeInTheDocument();
    hooks.useEdges.mockReturnValue(
      fakeQuery({ ...EDGE_ROWS_FIXTURE, items: [], facets: { total: 0, matched: 0, items: [] } }),
    );
    rerender(<EdgeList onSelect={vi.fn()} search={{}} onSearchChange={vi.fn()} />);
    expect(screen.getByText('No edge is declared.')).toBeInTheDocument();
  });
});
