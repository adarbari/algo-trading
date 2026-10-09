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
  useScreenerResults: vi.fn(),
}));
vi.mock('@/entities/screen', async (importOriginal) => {
  return {
    ...(await importOriginal<Record<string, unknown>>()),
    useScreeners: hooks.useScreeners,
    useMyScreeners: hooks.useMyScreeners,
    useScreenerRuns: hooks.useScreenerRuns,
    useScreenerResults: hooks.useScreenerResults,
    useCriterionLines: () => ({
      isPending: false,
      lines: [{ id: 'iv', label: 'IV rank', rule: '≥ 50', mode: 'hard' }],
    }),
  };
});
vi.mock('@/entities/edge', async () => {
  const { Text } = await import('@algotrade/ui');
  return {
    ScreenerEdgeName: ({ screenerId }: { screenerId: string }) => (
      <Text>{`edge of ${screenerId}`}</Text>
    ),
    ScreenerRecord: ({ screenerId }: { screenerId: string }) => (
      <Text>{`cell record of ${screenerId}`}</Text>
    ),
    useTrackRecords: () => ({
      isPending: false,
      isError: false,
      data: [{ edgeId: 'edge-1', edgeName: 'Edge one', notRun: null }],
    }),
    recordFigures: (entries: { edgeId: string; edgeName: string }[]) =>
      entries[0]
        ? {
            ...entries[0],
            hitRate: 0.6,
            baseRate: 0.5,
            liftPts: 12,
            sessions: 100,
            horizonSessions: 10,
          }
        : null,
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
  criteria: [{ id: 'iv', field: 'iv_rank', mode: 'hard' }],
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

const HIT = {
  instrumentId: 'EQ:1',
  decision: 'QUALIFIED',
  score: 91.5,
  reasons: 'Above the 50d high on volume',
  instrument: { symbol: 'AAPL', name: 'Apple Inc.' },
};

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
  hooks.useScreenerResults.mockReturnValue(
    fakeQuery({
      screener: {
        latestRun: {
          status: 'complete',
          coverage: 'FULL',
          unavailable: [],
          results: { results: [HIT] },
        },
      },
    }),
  );
});

const setup = () => {
  const onOpen = vi.fn();
  const onEdit = vi.fn();
  const onOpenTicker = vi.fn();
  const onOpenEdge = vi.fn();
  const view = render(
    <TestQueryProvider>
      <ScreenerList
        onOpen={onOpen}
        onEdit={onEdit}
        onOpenTicker={onOpenTicker}
        onOpenEdge={onOpenEdge}
      />
    </TestQueryProvider>,
  );
  return { onOpen, onEdit, onOpenTicker, onOpenEdge, ...view };
};
const toggle = (name: RegExp) => screen.getByRole('button', { name });

/** Open a row and wait for its lazily loaded detail. */
const openRow = async (name: RegExp) => {
  await userEvent.click(toggle(name));
  await screen.findByRole('heading', { level: 3, name: 'Criteria' });
};

describe('ScreenerList', () => {
  it('lists mine and presets in one list with type pills, hits and runs', async () => {
    const { container } = setup();
    const table = screen.getByRole('table', { name: 'Screeners' });
    expect(within(table).getAllByRole('button')).toHaveLength(5);
    expect(toggle(/^Name of my-vrp Mine/)).toHaveTextContent('edge of my-vrp');
    expect(screen.getAllByText('+2').length).toBeGreaterThan(0);
    expect(screen.getAllByText('−1').length).toBeGreaterThan(0);
    expect(screen.getAllByText('2026-10-07').length).toBeGreaterThan(0);
    expect(screen.getByText('12')).toBeInTheDocument();
    expect(
      within(table).getByRole('img', { name: /Decisions of vrp_scanner: Qualified 12/ }),
    ).toBeInTheDocument();
    expect(
      within(table).getByRole('img', { name: /^my-vrp picks, last 3 sessions/ }),
    ).toBeInTheDocument();
    expect(screen.getAllByText('No run today')).toHaveLength(1);
    expect(toggle(/^Name of broken Mine/)).toHaveTextContent('Does not resolve');
    expect(toggle(/^idea Mine/)).toHaveTextContent('Draft');
    expect(screen.getByText('cell record of my-vrp')).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it('narrows by segment and by search', async () => {
    setup();
    await userEvent.click(screen.getByRole('radio', { name: 'Presets' }));
    expect(screen.getAllByRole('button', { expanded: false })).toHaveLength(2);
    await userEvent.click(screen.getByRole('radio', { name: 'All' }));
    await userEvent.type(screen.getByRole('searchbox', { name: 'Search screeners' }), 'vrp');
    expect(screen.getAllByRole('button', { expanded: false })).toHaveLength(2);
    await userEvent.type(screen.getByRole('searchbox', { name: 'Search screeners' }), 'zzz');
    expect(screen.getByText('No screener matches')).toBeInTheDocument();
  });

  it('opens one row at a time and loads the hits only for the open row', async () => {
    setup();
    expect(hooks.useScreenerResults).not.toHaveBeenCalled();
    await openRow(/^Name of my-vrp/);
    expect(toggle(/^Name of my-vrp/)).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('IV rank')).toBeInTheDocument();
    expect(screen.getByText('≥ 50')).toBeInTheDocument();
    expect(screen.getByText('AAPL')).toBeInTheDocument();
    expect(screen.getByText('Apple Inc.')).toBeInTheDocument();
    expect(screen.getByText('Above the 50d high on volume')).toBeInTheDocument();
    expect(screen.getByText('60.0%')).toBeInTheDocument();
    await openRow(/^Name of vrp_scanner/);
    expect(toggle(/^Name of my-vrp/)).toHaveAttribute('aria-expanded', 'false');
    expect(toggle(/^Name of vrp_scanner/)).toHaveAttribute('aria-expanded', 'true');
  });

  it('offers View N hits, Edit criteria, Duplicate and Delete on one of yours', async () => {
    const { onOpen, onEdit } = setup();
    await openRow(/^Name of my-vrp/);
    await userEvent.click(screen.getByRole('button', { name: 'View 3 hits' }));
    expect(onOpen).toHaveBeenCalledWith('my-vrp');
    await userEvent.click(screen.getByRole('button', { name: 'Edit criteria' }));
    expect(onEdit).toHaveBeenCalledWith('my-vrp');
    await userEvent.click(screen.getByRole('button', { name: 'Duplicate' }));
    await userEvent.click(screen.getByRole('button', { name: 'finish duplicate of my-vrp' }));
    expect(onEdit).toHaveBeenCalledWith('copy-of-my-vrp');
    await userEvent.click(screen.getByRole('button', { name: 'Delete my-vrp' }));
    await userEvent.click(screen.getByRole('button', { name: 'confirm delete of my-vrp' }));
    expect(screen.queryByRole('button', { name: /confirm delete/ })).toBeNull();
  });

  it('opens a hit in Explore through its screener and the edge evidence', async () => {
    const { onOpenTicker, onOpenEdge } = setup();
    await openRow(/^Name of my-vrp/);
    await userEvent.click(screen.getByRole('button', { name: 'Open AAPL in Explore' }));
    expect(onOpenTicker).toHaveBeenCalledWith('AAPL', 'my-vrp');
    await userEvent.click(screen.getByRole('button', { name: 'Edge evidence' }));
    expect(onOpenEdge).toHaveBeenCalledWith('edge-1');
  });

  it('says the run is partial in a notice line', async () => {
    hooks.useScreenerResults.mockReturnValue(
      fakeQuery({
        screener: {
          latestRun: {
            status: 'partial',
            coverage: 'PARTIAL',
            unavailable: [{ kindText: 'a table is missing' }],
            results: { results: [HIT] },
          },
        },
      }),
    );
    setup();
    await openRow(/^Name of my-vrp/);
    expect(screen.getByRole('button', { name: /Partial run/ })).toBeInTheDocument();
  });

  it('says a screener with no run is not run, in its open row', async () => {
    setup();
    await openRow(/^Name of broken/);
    expect(screen.getByRole('button', { name: /Not run/ })).toBeInTheDocument();
  });

  it('offers Duplicate to edit on a preset, never Edit criteria or Delete', async () => {
    const { onEdit } = setup();
    await openRow(/^Name of vrp_scanner/);
    expect(screen.queryByRole('button', { name: 'Edit criteria' })).toBeNull();
    expect(screen.queryByRole('button', { name: /^Delete/ })).toBeNull();
    expect(screen.getByRole('link', { name: 'Playbook' })).toHaveAttribute(
      'href',
      '/guide/playbooks/vrp_scanner',
    );
    await userEvent.click(screen.getByRole('button', { name: 'Duplicate to edit' }));
    await userEvent.click(screen.getByRole('button', { name: 'finish copy of vrp_scanner' }));
    expect(onEdit).toHaveBeenCalledWith('copy-of-vrp_scanner');
  });

  it('opens a Python preset with no actions', async () => {
    setup();
    await openRow(/^short_premium/);
    expect(screen.queryByRole('button', { name: /Duplicate|View/ })).toBeNull();
  });

  it('says when the list failed to load', () => {
    hooks.useScreeners.mockReturnValue(fakeQuery(undefined, { isError: true }));
    setup();
    expect(screen.getByText('The screeners failed to load.')).toBeInTheDocument();
  });
});
