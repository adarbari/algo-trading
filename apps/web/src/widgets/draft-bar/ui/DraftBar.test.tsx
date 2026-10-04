import { ToastProvider } from '@algotrade/ui';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { api, TestQueryProvider } from '@/shared/api';
import { expectNoA11yViolations } from '@/shared/lib/testing';

import { DraftBar } from './DraftBar';

const state = vi.hoisted(() => ({ builder: {} }));

vi.mock('@/features/screener-builder', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useScreenerBuilder: () => state.builder,
}));
vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, api: { POST: vi.fn(), PUT: vi.fn() } };
});

const POST = vi.mocked(api.POST);

const save = vi.fn(() => Promise.resolve());
const discard = vi.fn(() => Promise.resolve());
const builder = (patch: Record<string, unknown> = {}, detail: Record<string, unknown> = {}) => ({
  id: 'my-vrp',
  readOnly: false,
  dirty: false,
  saving: false,
  discarding: false,
  nextVersion: 2,
  criteria: [{ id: 'a' }],
  save,
  discard,
  detail: {
    draft: { id: 'my-vrp' },
    draft_error: null,
    versions: [1],
    latest: 1,
    schedule: 'nightly',
    preset: { preset_id: 'vrp', pinned: 1, current: 1, rebase_available: false },
    ...detail,
  },
  ...patch,
});

function setup() {
  const onOpen = vi.fn();
  const view = render(
    <ToastProvider>
      <TestQueryProvider>
        <DraftBar onOpen={onOpen} />
      </TestQueryProvider>
    </ToastProvider>,
  );
  return { onOpen, ...view };
}

beforeEach(() => {
  save.mockClear();
  discard.mockClear();
  POST.mockReset();
  state.builder = builder();
});

describe('DraftBar', () => {
  it('shows the state, the preset and the separate actions', async () => {
    const { container } = setup();
    expect(screen.getByRole('heading', { level: 1, name: 'my-vrp' })).toBeInTheDocument();
    expect(screen.getByText('DRAFT v2')).toBeInTheDocument();
    expect(screen.getByText('based on preset vrp v1')).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: 'Run nightly' })).toBeChecked();
    expect(screen.getByRole('button', { name: 'Save draft' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Finalize v2' })).toBeEnabled();
    await expectNoA11yViolations(container);
  });

  it('says unsaved changes and saves or discards them', async () => {
    state.builder = builder({ dirty: true });
    setup();
    expect(screen.getByText('DRAFT v2 · unsaved changes')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Save draft' }));
    expect(save).toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: 'Discard' }));
    expect(discard).toHaveBeenCalled();
  });

  it('finalizes after saving the edits', async () => {
    state.builder = builder({ dirty: true });
    POST.mockResolvedValue({
      data: { screener_id: 'my-vrp', version: 2, hash: 'h' },
      response: new Response(null, { status: 200 }),
    });
    setup();
    await userEvent.click(screen.getByRole('button', { name: 'Finalize v2' }));
    expect(await screen.findByText('Finalised v2')).toBeInTheDocument();
    expect(save).toHaveBeenCalled();
  });

  it('cannot finalize without criteria', () => {
    state.builder = builder({ criteria: [] });
    setup();
    expect(screen.getByRole('button', { name: 'Finalize v2' })).toBeDisabled();
  });

  it('offers a rebase when the preset has a newer version, once the edits are saved', () => {
    state.builder = builder(
      { dirty: true },
      { preset: { preset_id: 'vrp', pinned: 1, current: 2, rebase_available: true } },
    );
    setup();
    expect(screen.getByText('Rebase available')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Rebase on v2' })).toBeDisabled();
  });

  it('shows a preset that was not copied read-only with Copy to my screeners', async () => {
    state.builder = builder(
      { readOnly: true },
      { draft: null, versions: [], latest: null, schedule: null, preset: null },
    );
    const { onOpen } = setup();
    expect(screen.getAllByText('Site preset')).toHaveLength(2); // the badge and the banner title
    expect(screen.queryByRole('button', { name: 'Save draft' })).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: 'Copy to my screeners' }));
    expect(screen.getByRole('dialog', { name: 'Copy to my screeners' })).toBeInTheDocument();
    expect(onOpen).not.toHaveBeenCalled();
  });

  it('warns when the saved draft would not finalize', () => {
    state.builder = builder(
      {},
      { draft_error: 'my-vrp.criteria: needs at least one enabled criterion' },
    );
    setup();
    expect(screen.getByText('This draft would not finalize')).toBeInTheDocument();
  });
});
