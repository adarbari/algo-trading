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
vi.mock('@/entities/screen', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useScreeners: hooks.useScreeners,
  useMyScreeners: hooks.useMyScreeners,
  useScreenerRuns: hooks.useScreenerRuns,
  useScreenerResults: hooks.useScreenerResults,
}));
vi.mock('@/entities/edge', async () => {
  const { Text } = await import('@algotrade/ui');
  return {
    ScreenerTrackChip: ({ screenerId }: { screenerId: string }) => (
      <Text>{`record of ${screenerId}`}</Text>
    ),
    ScreenerOdds: ({ screenerId }: { screenerId: string }) => (
      <Text>{`odds of ${screenerId}`}</Text>
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
  criteria: [{ id: 'iv', field: 'iv_rank', mode: 'hard' }],
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
        },
});

const HIT = {
  instrumentId: 'EQ:1',
  decision: 'QUALIFIED',
  instrument: { symbol: 'AAPL' },
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
    fakeQuery({ screener: { latestRun: { results: { results: [HIT] } } } }),
  );
});

const setup = () => {
  const onOpen = vi.fn();
  const onEdit = vi.fn();
  const view = render(
    <TestQueryProvider>
      <ScreenerList onOpen={onOpen} onEdit={onEdit} />
    </TestQueryProvider>,
  );
  return { onOpen, onEdit, ...view };
};
const toggle = (name: RegExp) => screen.getByRole('button', { name });

describe('ScreenerList', () => {
  it('lists mine and presets in one list with type pills, hits and runs', async () => {
    const { container } = setup();
    const list = screen.getByRole('list', { name: 'Screeners' });
    expect(within(list).getAllByRole('listitem')).toHaveLength(5);
    expect(toggle(/^my-vrp Mine/)).toHaveTextContent('3');
    expect(toggle(/^vrp_scanner Preset/)).toHaveTextContent('Run 2026-10-07');
    expect(toggle(/^vrp_scanner Preset/)).toHaveTextContent('12');
    expect(toggle(/^broken Mine/)).toHaveTextContent('No run today');
    expect(toggle(/^broken Mine/)).toHaveTextContent('Does not resolve');
    expect(toggle(/^idea Mine/)).toHaveTextContent('Draft');
    expect(screen.getByText('record of my-vrp')).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it('narrows by segment and by search', async () => {
    setup();
    await userEvent.click(screen.getByRole('radio', { name: 'Presets' }));
    expect(screen.getAllByRole('listitem')).toHaveLength(2);
    await userEvent.click(screen.getByRole('radio', { name: 'All' }));
    await userEvent.type(screen.getByRole('searchbox', { name: 'Search screeners' }), 'vrp');
    expect(screen.getAllByRole('listitem')).toHaveLength(2);
    await userEvent.type(screen.getByRole('searchbox', { name: 'Search screeners' }), 'zzz');
    expect(screen.getByText('No screener matches')).toBeInTheDocument();
  });

  it('opens one row at a time and loads the hits only for the open row', async () => {
    setup();
    expect(hooks.useScreenerResults).not.toHaveBeenCalled();
    await userEvent.click(toggle(/^my-vrp/));
    expect(toggle(/^my-vrp/)).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('iv_rank')).toBeInTheDocument();
    expect(screen.getByText('AAPL')).toBeInTheDocument();
    expect(screen.getByText('odds of my-vrp')).toBeInTheDocument();
    await userEvent.click(toggle(/^vrp_scanner/));
    expect(toggle(/^my-vrp/)).toHaveAttribute('aria-expanded', 'false');
    expect(toggle(/^vrp_scanner/)).toHaveAttribute('aria-expanded', 'true');
  });

  it('offers View N hits, Edit criteria, Duplicate and Delete on one of yours', async () => {
    const { onOpen, onEdit } = setup();
    await userEvent.click(toggle(/^my-vrp/));
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

  it('offers Duplicate to edit on a preset, never Edit criteria or Delete', async () => {
    const { onEdit } = setup();
    await userEvent.click(toggle(/^vrp_scanner/));
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
    await userEvent.click(toggle(/^short_premium/));
    expect(screen.queryByRole('button', { name: /Duplicate|View/ })).toBeNull();
  });

  it('says when the list failed to load', () => {
    hooks.useScreeners.mockReturnValue(fakeQuery(undefined, { isError: true }));
    setup();
    expect(screen.getByText('The screeners failed to load.')).toBeInTheDocument();
  });
});
