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
  preset: null,
  dirty: false,
  saving: false,
  discarding: false,
  nextVersion: 2,
  criteria: [{ id: 'a' }],
  save,
  discard,
  detail: {
    draft: { id: 'my-vrp' },
    draftError: null,
    versions: [1],
    latest: 1,
    preset: { presetId: 'vrp', pinned: 1, current: 1, rebaseAvailable: false },
    ...detail,
  },
  ...patch,
});

function setup(onDeleted?: () => void, onReturn?: () => void) {
  return render(
    <ToastProvider>
      <TestQueryProvider>
        <DraftBar {...(onDeleted ? { onDeleted } : {})} {...(onReturn ? { onReturn } : {})} />
      </TestQueryProvider>
    </ToastProvider>,
  );
}

beforeEach(() => {
  save.mockClear();
  discard.mockClear();
  POST.mockReset();
  state.builder = builder();
});

describe('DraftBar', () => {
  it('offers "Save and return to edge" only when opened from an edge: it saves unsaved edits first', async () => {
    const { unmount } = setup();
    expect(screen.queryByRole('button', { name: 'Save and return to edge' })).toBeNull();
    unmount();
    const onReturn = vi.fn();
    state.builder = builder({ dirty: true });
    setup(undefined, onReturn);
    await userEvent.click(screen.getByRole('button', { name: 'Save and return to edge' }));
    await vi.waitFor(() => {
      expect(onReturn).toHaveBeenCalled();
    });
    expect(save).toHaveBeenCalledOnce();
  });

  it('returns without a save when nothing changed', async () => {
    const onReturn = vi.fn();
    setup(undefined, onReturn);
    await userEvent.click(screen.getByRole('button', { name: 'Save and return to edge' }));
    await vi.waitFor(() => {
      expect(onReturn).toHaveBeenCalled();
    });
    expect(save).not.toHaveBeenCalled();
  });

  it('shows the state, the preset and the separate actions', async () => {
    const { container } = setup();
    expect(screen.getByRole('heading', { level: 1, name: 'my-vrp' })).toBeInTheDocument();
    expect(screen.getByText('DRAFT v2')).toBeInTheDocument();
    expect(screen.getByText('Your copy of vrp v1')).toBeInTheDocument();
    expect(screen.queryByRole('checkbox', { name: 'Run nightly' })).toBeNull(); // no switch (ADR 0033)
    expect(screen.getByRole('button', { name: 'Save draft' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Finalize v2' })).toBeEnabled();
    await expectNoA11yViolations(container);
  });

  it('links a copy of a site preset, and the preset itself, to the preset’s playbook', () => {
    const { unmount } = setup();
    expect(screen.getByRole('link', { name: 'Playbook' })).toHaveAttribute(
      'href',
      '/guide/playbooks/vrp',
    );
    unmount();
    state.builder = builder({ id: 'vrp_scanner', preset: { id: 'vrp_scanner', version: 1 } });
    setup();
    expect(screen.getByRole('link', { name: 'Playbook' })).toHaveAttribute(
      'href',
      '/guide/playbooks/vrp_scanner',
    );
  });

  it('has no playbook link on a screen that copies no preset', () => {
    state.builder = builder({}, { preset: null });
    setup();
    expect(screen.queryByRole('link', { name: 'Playbook' })).toBeNull();
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

  it('offers Delete for your own screener when the page can leave it', () => {
    setup();
    expect(screen.queryByRole('button', { name: 'Delete' })).toBeNull();
    setup(vi.fn());
    expect(screen.getByRole('button', { name: 'Delete' })).toBeEnabled();
  });

  it('cannot finalize without criteria', () => {
    state.builder = builder({ criteria: [] });
    setup();
    expect(screen.getByRole('button', { name: 'Finalize v2' })).toBeDisabled();
  });

  it('offers a rebase when the preset has a newer version, once the edits are saved', () => {
    state.builder = builder(
      { dirty: true },
      { preset: { presetId: 'vrp', pinned: 1, current: 2, rebaseAvailable: true } },
    );
    setup();
    expect(screen.getByText('Rebase available')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Rebase on v2' })).toBeDisabled();
  });

  const untouched = () =>
    builder(
      { preset: { id: 'vrp', version: 3 } },
      {
        draft: null,
        versions: [],
        latest: null,
        preset: { presetId: 'vrp', pinned: null, current: 3, rebaseAvailable: false },
      },
    );

  it('shows a preset as it is, with the same actions: no read-only mode', async () => {
    state.builder = untouched();
    const { container } = setup();
    expect(screen.getAllByText('Site preset')).toHaveLength(2); // the badge and the banner title
    expect(
      screen.getByText(/This is the site preset v3 with its live preview/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Your copy of/)).toBeNull();
    expect(screen.getByRole('button', { name: 'Save draft' })).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Copy to my screeners' })).toBeNull();
    await expectNoA11yViolations(container);
  });

  it('offers no Delete for a site preset not copied yet (it changes by PR)', () => {
    state.builder = untouched();
    setup(vi.fn());
    expect(screen.queryByRole('button', { name: 'Delete' })).toBeNull();
  });

  it('says it is your copy as soon as the first edit is made', () => {
    state.builder = {
      ...untouched(),
      dirty: true,
    };
    setup();
    expect(screen.getByText('Your copy of vrp v3')).toBeInTheDocument();
    expect(screen.getByText('DRAFT v2 · unsaved changes')).toBeInTheDocument();
    expect(screen.queryByText(/This is the site preset/)).toBeNull();
  });

  it('warns when the saved draft would not finalize', () => {
    state.builder = builder(
      {},
      { draftError: 'my-vrp.criteria: needs at least one enabled criterion' },
    );
    setup();
    expect(screen.getByText('This draft would not finalize')).toBeInTheDocument();
  });
});
