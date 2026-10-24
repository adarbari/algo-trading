import { render, screen, within } from '@testing-library/react';
import { useState } from 'react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ScreenerListItem, ScreenerRunSummary, ScreenerSummary } from '@/entities/screen';
import { filterSearch } from '@/features/filter-bar';
import { gql, TestQueryProvider } from '@/shared/api';
import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { ScreenerList, type ScreenerListSearch } from './ScreenerList';

vi.mock('@/shared/api', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  gql: vi.fn(),
}));

const hooks = vi.hoisted(() => ({
  useScreeners: vi.fn(),
  useMyScreeners: vi.fn(),
  useScreenerRuns: vi.fn(),
  useScreenerList: vi.fn(),
}));
vi.mock('@/entities/screen', async (importOriginal) => {
  return {
    ...(await importOriginal<Record<string, unknown>>()),
    useScreeners: hooks.useScreeners,
    useMyScreeners: hooks.useMyScreeners,
    useScreenerRuns: hooks.useScreenerRuns,
    useScreenerList: hooks.useScreenerList,
  };
});
vi.mock('@/entities/edge', async () => {
  const { Button, ExpandLink, Text } = await import('@algotrade/ui');
  return {
    ScreenerEvidenceCell: ({
      screenerId,
      open,
      onOpenChange,
    }: {
      screenerId: string;
      open: boolean;
      onOpenChange: (open: boolean) => void;
    }) =>
      screenerId === 'idea' ? (
        <Text>Not part of an edge</Text>
      ) : (
        <ExpandLink open={open} onOpenChange={onOpenChange}>{`Win of ${screenerId}`}</ExpandLink>
      ),
    ScreenerEvidenceDetail: ({
      screenerId,
      onOpenEdge,
    }: {
      screenerId: string;
      onOpenEdge: (edgeId: string) => void;
    }) => (
      <Button
        onClick={() => {
          onOpenEdge(`edge-of-${screenerId}`);
        }}
      >{`edges of ${screenerId}`}</Button>
    ),
  };
});
vi.mock('@/features/screener-copy', async () => {
  const { Button } = await import('@algotrade/ui');
  return {
    CopyPresetDialog: ({
      preset,
      own,
      onCopied,
    }: {
      preset: string;
      own: boolean;
      onCopied: (id: string) => void;
    }) => (
      <Button
        onClick={() => {
          onCopied(`copy-of-${preset}`);
        }}
      >
        {`finish ${own ? 'duplicate' : 'copy'} of ${preset}`}
      </Button>
    ),
  };
});
vi.mock('@/features/screener-delete', async () => {
  const { Button } = await import('@algotrade/ui');
  return {
    DeleteScreenerDialog: ({
      screenerId,
      onDeleted,
    }: {
      screenerId: string;
      onDeleted: () => void;
    }) => <Button onClick={onDeleted}>{`confirm delete of ${screenerId}`}</Button>,
  };
});

stubElementSize();

const config = (
  configId: string,
  scope: string,
  impl = 'rules',
  patch: Partial<ScreenerSummary> = {},
): ScreenerSummary => ({
  configId,
  scope,
  kind: 'screener',
  impl,
  selection: null,
  hash: 'h',
  error: null,
  ...patch,
});
const own = (screenerId: string, patch: Partial<ScreenerListItem> = {}): ScreenerListItem => ({
  screenerId,
  status: 'FINAL',
  latest: 1,
  hasDraft: false,
  presetId: null,
  ...patch,
});
const summary = (
  id: string,
  picked: number | null,
  description: string | null = null,
): ScreenerRunSummary => ({
  id,
  name: `Name of ${id}`,
  description,
  criteria: [{ id: 'iv', field: 'iv_rank', mode: 'hard', op: 'gte', value: 50 }],
  pickHistory: [
    { session: '2026-10-06', picked: 1 },
    { session: '2026-10-07', picked: null },
    { session: '2026-10-08', picked: picked },
  ],
  notRun: picked === null ? { kindText: 'not run' } : null,
  latestRun:
    picked === null
      ? null
      : {
          runId: 'r',
          session: '2026-10-07',
          picked,
          paused: 0,
          decisions: [{ decision: 'QUALIFIED', count: picked }],
          changes: [
            { change: 'new', count: 2 },
            { change: 'dropped', count: 1 },
          ],
        },
});

const FILTER_SET = {
  filterSet: {
    surface: 'screeners',
    label: 'Screeners',
    filters: [
      {
        id: 'owner',
        label: 'Owner',
        group: 'SETUP',
        kind: 'PICK',
        guide: 'term:filter_owner',
        options: [
          { value: 'mine', label: 'Mine' },
          { value: 'site', label: 'Presets' },
        ],
        bins: [],
        windowUnit: null,
      },
    ],
  },
};
const facets = (matched: number) => ({ total: 4, matched, items: [] });
/** The server's answer for the narrowing: the ids that stay. */
const narrowing = (ids: string[]) => fakeQuery({ ids: new Set(ids), facets: facets(ids.length) });

beforeEach(() => {
  hooks.useScreenerList.mockReset();
  hooks.useScreenerList.mockReturnValue(narrowing(['vrp_scanner', 'short_premium', 'my-vrp']));
  vi.mocked(gql).mockResolvedValue(FILTER_SET);
  hooks.useScreeners.mockReturnValue(
    fakeQuery([
      config('vrp_scanner', 'site'),
      config('short_premium', 'site', 'short_premium_liquidity'),
      config('my-vrp', 'u'),
      config('broken', 'u', 'rules', { error: 'unknown field' }),
    ]),
  );
  hooks.useMyScreeners.mockReturnValue(
    fakeQuery([
      own('my-vrp', { presetId: 'vrp_scanner' }),
      own('broken'),
      own('idea', { status: 'DRAFT', latest: null }),
    ]),
  );
  hooks.useScreenerRuns.mockReturnValue(
    fakeQuery({
      session: '2026-10-07',
      byId: new Map([
        ['vrp_scanner', summary('vrp_scanner', 12)],
        ['my-vrp', summary('my-vrp', 3, 'Rich premium in calm names')],
        ['broken', summary('broken', null)],
      ]),
    }),
  );
});

/** The page's job: the search params held in state, a patch applied to them. */
function Held({
  handlers,
  initial,
}: {
  handlers: { onOpen: () => void; onEdit: () => void; onOpenEdge: () => void };
  initial: ScreenerListSearch;
}) {
  const [search, setSearch] = useState(initial);
  return (
    <ScreenerList
      {...handlers}
      search={search}
      onSearchChange={(patch) => {
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

const setup = (initial: ScreenerListSearch = {}) => {
  const onOpen = vi.fn();
  const onEdit = vi.fn();
  const onOpenEdge = vi.fn();
  const view = render(
    <TestQueryProvider>
      <Held handlers={{ onOpen, onEdit, onOpenEdge }} initial={initial} />
    </TestQueryProvider>,
  );
  return { onOpen, onEdit, onOpenEdge, ...view };
};

/** What the narrowing read last asked: the filters in force and the search text. */
const lastAsked = () => hooks.useScreenerList.mock.calls.at(-1) as [{ id: string }[], string];

const rowOf = (text: string) =>
  within(screen.getByRole('table', { name: 'Screeners' }))
    .getAllByRole('row')
    .find((r) => r.textContent.includes(text)) as HTMLElement;

describe('ScreenerList', () => {
  it('lists mine and presets with kind pills, last run, evidence and picks', async () => {
    const { container } = setup();
    const table = screen.getByRole('table', { name: 'Screeners' });
    expect(
      within(table)
        .getAllByRole('columnheader')
        .map((h) => h.textContent),
    ).toEqual(['Screener and what it finds', 'Evidence and edges', 'Picks today', 'Actions']);
    expect(within(table).getByText('Name of my-vrp')).toBeInTheDocument();
    expect(screen.getAllByText('Mine').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Preset').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Last run 2026-10-07').length).toBeGreaterThan(0);
    expect(
      screen.getByRole('button', { name: 'Open Name of vrp_scanner: 12 picks' }),
    ).toHaveTextContent('12 picks');
    expect(screen.getAllByText('+2').length).toBeGreaterThan(0);
    expect(screen.getAllByText('−1').length).toBeGreaterThan(0);
    expect(screen.getAllByText('No run today')).toHaveLength(1);
    expect(screen.getByText('Does not resolve')).toBeInTheDocument();
    expect(screen.getByText('Draft')).toBeInTheDocument();
    expect(screen.getByText('Not part of an edge')).toBeInTheDocument();
    expect(screen.getByText('Built in code')).toBeInTheDocument();
    // No decisions column and no 30-day history any more.
    expect(screen.queryByText('Decisions')).toBeNull();
    expect(screen.queryByText('30d picks')).toBeNull();
    await expectNoA11yViolations(container);
  });

  it('shows the description under the name, clamped, and an add link only on your own without one', async () => {
    const { onEdit } = setup();
    expect(screen.getByText('Rich premium in calm names').parentElement).toHaveAttribute(
      'title',
      'Rich premium in calm names',
    ); // inside a LineClamp, which keeps the full text as its tooltip
    // Only `broken` is yours, resolved and without a description; presets and the draft-only idea get none.
    expect(screen.getAllByRole('button', { name: 'Add a description' })).toHaveLength(1);
    await userEvent.click(screen.getByRole('button', { name: 'Add a description' }));
    expect(onEdit).toHaveBeenCalledWith('broken');
  });

  it('does not expand as a whole: only the evidence headline opens the edges', async () => {
    setup();
    expect(screen.queryByRole('button', { name: /edges of/ })).toBeNull();
    await userEvent.click(screen.getByText('Name of my-vrp'));
    expect(screen.queryByRole('button', { name: /edges of/ })).toBeNull();
  });

  it('opens one evidence block at a time, in place', async () => {
    const { onOpenEdge } = setup();
    const mine = screen.getByRole('button', { name: 'Win of my-vrp' });
    const preset = screen.getByRole('button', { name: 'Win of vrp_scanner' });
    await userEvent.click(mine);
    expect(mine).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('button', { name: 'edges of my-vrp' })).toBeInTheDocument();
    await userEvent.click(preset);
    expect(mine).toHaveAttribute('aria-expanded', 'false');
    expect(preset).toHaveAttribute('aria-expanded', 'true');
    expect(screen.queryByRole('button', { name: 'edges of my-vrp' })).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: 'edges of vrp_scanner' }));
    expect(onOpenEdge).toHaveBeenCalledWith('edge-of-vrp_scanner');
  });

  it('keeps the rows the server names for the filters in the URL, with the filter bar', async () => {
    hooks.useScreenerList.mockReturnValue(narrowing(['vrp_scanner', 'short_premium']));
    setup({ f: 'owner:site' });
    expect(lastAsked()[0]).toEqual([expect.objectContaining({ id: 'owner' })]);
    expect(screen.getAllByRole('button', { name: /^Win of/ })).toHaveLength(2);
    expect(rowOf('Name of my-vrp')).toBeUndefined();
    expect(await screen.findByRole('button', { name: /Setup/ })).toBeInTheDocument();
  });

  it('shows every row, drafts too, when nothing narrows, and asks for the typed search', async () => {
    setup();
    expect(rowOf('idea')).toBeDefined();
    await userEvent.type(screen.getByRole('searchbox', { name: 'Search screeners' }), 'vrp');
    expect(screen.getByRole('searchbox', { name: 'Search screeners' })).toHaveValue('vrp');
    await vi.waitFor(() => {
      expect(lastAsked()[1]).toBe('vrp');
    });
  });

  it('offers the way back when the filters leave nothing, and when only the search does', async () => {
    hooks.useScreenerList.mockReturnValue(narrowing([]));
    const { unmount } = setup({ f: 'owner:mine', q: 'zzz' });
    expect(await screen.findByText('No screeners match this filter')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Clear the search' }));
    expect(screen.getByRole('searchbox', { name: 'Search screeners' })).toHaveValue('');
    unmount();
    setup({ q: 'zzz' });
    expect(screen.getByText('No screener matches "zzz"')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Clear the search' }));
    expect(screen.queryByText(/No screener matches/)).not.toBeInTheDocument();
  });

  it('opens the screener from the picks link, or "Not run" when there is no run, for every screener', async () => {
    const { onOpen } = setup();
    await userEvent.click(screen.getByRole('button', { name: 'Open Name of my-vrp: 3 picks' }));
    expect(onOpen).toHaveBeenLastCalledWith('my-vrp');
    // A preset, a Python preset and a screener with no run are all reachable; there is no View action.
    await userEvent.click(within(rowOf('short_premium')).getByRole('button', { name: /not run$/ }));
    expect(onOpen).toHaveBeenLastCalledWith('short_premium');
    await userEvent.click(within(rowOf('idea')).getByRole('button', { name: /not run$/ }));
    expect(onOpen).toHaveBeenLastCalledWith('idea');
    expect(screen.queryByRole('button', { name: 'View' })).toBeNull();
  });

  it('offers Edit criteria, Duplicate and Delete on one of yours, labelled', async () => {
    const { onEdit } = setup();
    const mine = within(rowOf('Name of my-vrp'));
    expect(mine.getByRole('group', { name: 'Actions of Name of my-vrp' })).toBeInTheDocument();
    await userEvent.click(mine.getByRole('button', { name: 'Edit criteria' }));
    expect(onEdit).toHaveBeenCalledWith('my-vrp');
    await userEvent.click(mine.getByRole('button', { name: 'Duplicate' }));
    await userEvent.click(screen.getByRole('button', { name: 'finish duplicate of my-vrp' }));
    expect(onEdit).toHaveBeenCalledWith('copy-of-my-vrp');
    await userEvent.click(mine.getByRole('button', { name: 'Delete' }));
    await userEvent.click(screen.getByRole('button', { name: 'confirm delete of my-vrp' }));
    expect(screen.queryByRole('button', { name: /confirm delete/ })).toBeNull();
  });

  it('offers Duplicate to edit and nothing else on a preset', async () => {
    const { onEdit } = setup();
    const preset = within(rowOf('Name of vrp_scanner'));
    expect(preset.queryByRole('button', { name: /Edit criteria|Delete/ })).toBeNull();
    expect(preset.getAllByRole('button', { name: /Duplicate/ })).toHaveLength(1);
    await userEvent.click(preset.getByRole('button', { name: 'Duplicate to edit' }));
    await userEvent.click(screen.getByRole('button', { name: 'finish copy of vrp_scanner' }));
    expect(onEdit).toHaveBeenCalledWith('copy-of-vrp_scanner');
  });

  it('gives a Python preset its evidence and the picks link, with no actions', () => {
    setup();
    const python = within(rowOf('short_premium'));
    expect(python.getByRole('button', { name: 'Win of short_premium' })).toBeInTheDocument();
    expect(python.getByText('Built in code')).toBeInTheDocument();
    expect(python.queryByRole('group')).toBeNull();
    expect(python.queryByRole('button', { name: /Duplicate|Edit|Delete/ })).toBeNull();
  });

  it('says when the list failed to load', () => {
    hooks.useScreeners.mockReturnValue(fakeQuery(undefined, { isError: true }));
    setup();
    expect(screen.getByText('The screeners failed to load.')).toBeInTheDocument();
  });
});
