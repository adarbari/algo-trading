import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ScreenerListItem, ScreenerSummary } from '@/entities/screen';
import { TestQueryProvider } from '@/shared/api';
import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { ScreenerList } from './ScreenerList';

const hooks = vi.hoisted(() => ({ useScreeners: vi.fn(), useMyScreeners: vi.fn() }));
vi.mock('@/entities/screen', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useScreeners: hooks.useScreeners,
  useMyScreeners: hooks.useMyScreeners,
}));
vi.mock('@/features/screener-copy', async () => {
  const { Button } = await import('@algotrade/ui');
  return {
    CopyPresetDialog: ({
      preset,
      onCopied,
    }: {
      preset: string;
      onCopied: (id: string) => void;
    }) => (
      <Button
        onClick={() => {
          onCopied(`my-${preset}`);
        }}
      >
        {`finish copy of ${preset}`}
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

const screener = (
  configId: string,
  scope: string,
  impl: string,
  patch: Partial<ScreenerSummary> = {},
): ScreenerSummary => ({
  configId,
  scope,
  kind: 'screener',
  impl,
  selection: 'liquid_optionable',
  hash: 'h',
  error: null,
  ...patch,
});
const LIST = [
  screener('vrp_scanner', 'site', 'rules'),
  screener('short_premium', 'site', 'short_premium_liquidity'),
  screener('my-vrp', 'abhinav', 'rules'),
  screener('broken', 'abhinav', 'rules', { error: 'unknown field' }),
];
const mine = (screenerId: string, patch: Partial<ScreenerListItem> = {}): ScreenerListItem => ({
  screenerId,
  status: 'FINAL',
  latest: 1,
  hasDraft: false,
  presetId: null,
  ...patch,
});
const MINE = [
  mine('my-vrp', { presetId: 'vrp_scanner', hasDraft: true, latest: 2 }),
  mine('broken'),
  mine('vrp_scanner', { status: 'DRAFT', latest: null, presetId: 'vrp_scanner' }),
];

beforeEach(() => {
  hooks.useScreeners.mockReturnValue(fakeQuery(LIST));
  hooks.useMyScreeners.mockReturnValue(fakeQuery(MINE));
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

describe('ScreenerList', () => {
  it('separates your screeners from the site presets', async () => {
    const { container } = setup();
    const mineTable = screen.getByRole('grid', { name: 'Your screeners' });
    expect(within(mineTable).getByRole('row', { name: /my-vrp/ })).toHaveTextContent('v2 + draft');
    expect(within(mineTable).getByRole('row', { name: /broken/ })).toHaveTextContent(
      'Does not resolve',
    );
    const presets = screen.getByRole('grid', { name: 'Site presets' });
    expect(within(presets).getByRole('row', { name: /short_premium/ })).toHaveTextContent('Python');
    expect(
      within(presets)
        .getByRole('row', { name: /short_premium/ })
        .querySelector('button'),
    ).toBeNull();
    await expectNoA11yViolations(container);
  });

  it('links every rule-screen preset to its playbook in the Guide, and Python screeners to none', () => {
    setup();
    const presets = within(screen.getByRole('grid', { name: 'Site presets' }));
    expect(
      within(presets.getByRole('row', { name: /vrp_scanner/ })).getByRole('link', {
        name: 'Playbook',
      }),
    ).toHaveAttribute('href', '/guide/playbooks/vrp_scanner');
    expect(
      within(presets.getByRole('row', { name: /short_premium/ })).queryByRole('link'),
    ).toBeNull();
  });

  it('lists a draft-only screener, with the preset it copies', () => {
    setup();
    const rows = within(screen.getByRole('grid', { name: 'Your screeners' })).getAllByRole('row');
    const row = rows.find((r) => r.textContent.startsWith('vrp_scanner'));
    if (!row) throw new Error('no draft row');
    expect(row).toHaveTextContent('DRAFT');
    expect(row).toHaveTextContent('vrp_scanner');
  });

  it('opens a screener to its results or its Builder, and a preset to its results', async () => {
    const { onOpen, onEdit } = setup();
    const mine = within(screen.getByRole('row', { name: /my-vrp/ }));
    await userEvent.click(mine.getByRole('button', { name: 'Edit' }));
    expect(onEdit).toHaveBeenCalledWith('my-vrp');
    await userEvent.click(mine.getByRole('button', { name: 'Results' }));
    expect(onOpen).toHaveBeenCalledWith('my-vrp');
    await userEvent.click(
      within(screen.getByRole('grid', { name: 'Site presets' })).getByRole('button', {
        name: 'Open',
      }),
    );
    expect(onOpen).toHaveBeenLastCalledWith('vrp_scanner');
  });

  it('opens a rule screener on a row click; a Python preset row does nothing', async () => {
    const { onOpen } = setup();
    const presets = within(screen.getByRole('grid', { name: 'Site presets' }));
    await userEvent.click(
      within(presets.getByRole('row', { name: /short_premium/ })).getByText('Python'),
    );
    expect(onOpen).not.toHaveBeenCalled();
    await userEvent.click(
      within(presets.getByRole('row', { name: /vrp_scanner/ })).getByText('Rules'),
    );
    expect(onOpen).toHaveBeenLastCalledWith('vrp_scanner');
    const mineRow = within(screen.getByRole('grid', { name: 'Your screeners' })).getByRole('row', {
      name: /my-vrp/,
    });
    await userEvent.click(within(mineRow).getByText('v2 + draft'));
    expect(onOpen).toHaveBeenLastCalledWith('my-vrp');
  });

  it('deletes one of your screeners after a confirmation; presets have no Delete', async () => {
    setup();
    const presets = within(screen.getByRole('grid', { name: 'Site presets' }));
    expect(presets.queryByRole('button', { name: /Delete/ })).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: 'Delete my-vrp' }));
    await userEvent.click(screen.getByRole('button', { name: 'confirm delete of my-vrp' }));
    expect(screen.queryByRole('button', { name: 'confirm delete of my-vrp' })).toBeNull();
  });

  it('copies a preset and opens the copy', async () => {
    const { onEdit } = setup();
    await userEvent.click(
      within(screen.getByRole('grid', { name: 'Site presets' })).getByRole('button', {
        name: 'Copy to my screeners',
      }),
    );
    await userEvent.click(screen.getByRole('button', { name: 'finish copy of vrp_scanner' }));
    expect(onEdit).toHaveBeenCalledWith('my-vrp_scanner');
    expect(screen.queryByRole('button', { name: /finish copy/ })).toBeNull();
  });

  it('says when you have none yet, and when the list failed to load', () => {
    hooks.useMyScreeners.mockReturnValue(fakeQuery([]));
    const { rerender } = setup();
    expect(
      screen.getByText('You have no screener yet. Create one, or open a preset and change it.'),
    ).toBeInTheDocument();
    hooks.useMyScreeners.mockReturnValue(fakeQuery(undefined, { isError: true, isPending: false }));
    rerender(
      <TestQueryProvider>
        <ScreenerList onOpen={vi.fn()} onEdit={vi.fn()} />
      </TestQueryProvider>,
    );
    expect(screen.getAllByText('The screeners failed to load.').length).toBeGreaterThan(0);
  });
});
