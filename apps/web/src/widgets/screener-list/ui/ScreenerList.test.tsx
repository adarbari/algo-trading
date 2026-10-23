import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ScreenerListItem, ScreenerRunSummary, ScreenerSummary } from '@/entities/screen';
import { TestQueryProvider } from '@/shared/api';
import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { ScreenerList } from './ScreenerList';

const hooks = vi.hoisted(() => ({
  useScreeners: vi.fn(),
  useMyScreeners: vi.fn(),
  useScreenerRuns: vi.fn(),
}));
vi.mock('@/entities/screen', async (importOriginal) => {
  return {
    ...(await importOriginal<Record<string, unknown>>()),
    useScreeners: hooks.useScreeners,
    useMyScreeners: hooks.useMyScreeners,
    useScreenerRuns: hooks.useScreenerRuns,
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
const summary = (id: string, picked: number | null): ScreenerRunSummary => ({
  id,
  name: `Name of ${id}`,
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

beforeEach(() => {
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
        ['my-vrp', summary('my-vrp', 3)],
        ['broken', summary('broken', null)],
      ]),
    }),
  );
});

const setup = () => {
  const onOpen = vi.fn();
  const onEdit = vi.fn();
  const onOpenEdge = vi.fn();
  const view = render(
    <TestQueryProvider>
      <ScreenerList onOpen={onOpen} onEdit={onEdit} onOpenEdge={onOpenEdge} />
    </TestQueryProvider>,
  );
  return { onOpen, onEdit, onOpenEdge, ...view };
};

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
    ).toEqual(['Screener', 'Evidence and edges', 'Picks today', 'Actions']);
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

  it('narrows by segment and by search', async () => {
    setup();
    await userEvent.click(screen.getByRole('radio', { name: 'Presets' }));
    expect(screen.getAllByRole('button', { name: /^Win of/ })).toHaveLength(2);
    await userEvent.click(screen.getByRole('radio', { name: 'All' }));
    await userEvent.type(screen.getByRole('searchbox', { name: 'Search screeners' }), 'vrp');
    expect(screen.getAllByRole('button', { name: /^Win of/ })).toHaveLength(2);
    await userEvent.type(screen.getByRole('searchbox', { name: 'Search screeners' }), 'zzz');
    expect(screen.getByText('No screener matches')).toBeInTheDocument();
  });

  it('links the picks to the screener, with a chevron, and View opens it for any screener', async () => {
    const { onOpen } = setup();
    await userEvent.click(screen.getByRole('button', { name: 'Open Name of my-vrp: 3 picks' }));
    expect(onOpen).toHaveBeenCalledWith('my-vrp');
    // Presets, a Python preset and a screener with no run can all be viewed.
    for (const id of ['vrp_scanner', 'short_premium', 'idea']) {
      await userEvent.click(within(rowOf(id)).getByRole('button', { name: 'View' }));
      expect(onOpen).toHaveBeenLastCalledWith(id);
    }
  });

  it('offers Edit, Duplicate and Delete on one of yours, labelled', async () => {
    const { onEdit } = setup();
    const mine = within(rowOf('Name of my-vrp'));
    await userEvent.click(mine.getByRole('button', { name: 'Edit' }));
    expect(onEdit).toHaveBeenCalledWith('my-vrp');
    await userEvent.click(mine.getByRole('button', { name: 'Duplicate' }));
    await userEvent.click(screen.getByRole('button', { name: 'finish duplicate of my-vrp' }));
    expect(onEdit).toHaveBeenCalledWith('copy-of-my-vrp');
    await userEvent.click(mine.getByRole('button', { name: 'Delete' }));
    await userEvent.click(screen.getByRole('button', { name: 'confirm delete of my-vrp' }));
    expect(screen.queryByRole('button', { name: /confirm delete/ })).toBeNull();
  });

  it('offers Duplicate to edit on a preset, never Edit or Delete', async () => {
    const { onEdit } = setup();
    const preset = within(rowOf('Name of vrp_scanner'));
    expect(preset.queryByRole('button', { name: 'Edit' })).toBeNull();
    expect(preset.queryByRole('button', { name: 'Delete' })).toBeNull();
    await userEvent.click(preset.getByRole('button', { name: 'Duplicate to edit' }));
    await userEvent.click(screen.getByRole('button', { name: 'finish copy of vrp_scanner' }));
    expect(onEdit).toHaveBeenCalledWith('copy-of-vrp_scanner');
  });

  it('gives a Python preset View and its evidence, with nothing to copy or edit', () => {
    setup();
    const python = within(rowOf('short_premium'));
    expect(python.getByRole('button', { name: 'View' })).toBeInTheDocument();
    expect(python.getByRole('button', { name: 'Win of short_premium' })).toBeInTheDocument();
    expect(python.getByText('Built in code')).toBeInTheDocument();
    expect(python.queryByRole('button', { name: /Duplicate|Edit|Delete/ })).toBeNull();
  });

  it('says when the list failed to load', () => {
    hooks.useScreeners.mockReturnValue(fakeQuery(undefined, { isError: true }));
    setup();
    expect(screen.getByText('The screeners failed to load.')).toBeInTheDocument();
  });
});
