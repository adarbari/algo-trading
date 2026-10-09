import { ToastProvider } from '@algotrade/ui';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { EDGES_FIXTURE } from '@/entities/edge';
import { api, TestQueryProvider } from '@/shared/api';
import { expectNoA11yViolations } from '@/shared/lib/testing';

import { EdgeActions } from './EdgeActions';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, api: { POST: vi.fn(), PUT: vi.fn() } };
});
const viewer = vi.hoisted(() => ({ role: 'trader' }));
vi.mock('@/entities/viewer', () => ({ useViewer: () => ({ data: { role: viewer.role } }) }));
vi.mock('@/features/guide-help', async () => {
  const { Text } = await import('@algotrade/ui');
  return { GuideHelp: ({ entry }: { entry: { id: string } }) => <Text>{`help ${entry.id}`}</Text> };
});

const POST = vi.mocked(api.POST);
const PUT = vi.mocked(api.PUT);
const ok = (data: unknown) => ({ data, response: new Response(null, { status: 200 }) }) as never;
const byId = (id: string) => {
  const found = EDGES_FIXTURE.edges.find((e) => e.id === id);
  if (!found) throw new Error(id);
  return found;
};

beforeEach(() => {
  POST.mockReset();
  PUT.mockReset();
  viewer.role = 'trader';
});

function setup(id: string, over: Record<string, unknown> = {}) {
  const onCloned = vi.fn();
  const view = render(
    <ToastProvider>
      <TestQueryProvider>
        <EdgeActions edge={{ ...byId(id), ...over }} onCloned={onCloned} />
      </TestQueryProvider>
    </ToastProvider>,
  );
  return { onCloned, ...view };
}

const buttons = () => screen.getAllByRole('button').map((b) => b.textContent);

describe('EdgeActions', () => {
  it('offers the moves of each state, and Show out-of-sample only for a hidden copy', () => {
    const { unmount } = setup('momentum_12_1');
    expect(buttons()).toEqual(['Clone', 'Follow', 'Reject']);
    unmount();
    const copy = setup('my_momentum', { state: 'following' });
    expect(buttons()).toEqual(['Clone', 'Retire', 'Back to researching', 'Show out-of-sample']);
    copy.unmount();
    setup('momentum_12_1', { state: 'rejected' });
    expect(buttons()).toEqual(['Clone', 'Back to researching']);
  });

  it('clones under a name and opens the copy', async () => {
    POST.mockResolvedValue(ok({ edge_id: 'mine', document: {} }));
    const { onCloned, baseElement } = setup('momentum_12_1');
    await userEvent.click(screen.getByRole('button', { name: 'Clone' }));
    const name = screen.getByRole('textbox', { name: 'Name of your copy' });
    expect(name).toHaveValue('my-momentum_12_1');
    await expectNoA11yViolations(baseElement);
    await userEvent.clear(name);
    await userEvent.type(name, 'mine');
    await userEvent.click(screen.getByRole('button', { name: 'Clone' }));
    await waitFor(() => {
      expect(onCloned).toHaveBeenCalledWith('mine');
    });
    expect(POST).toHaveBeenCalledWith('/edges/{edge_id}/copy', {
      params: { path: { edge_id: 'momentum_12_1' } },
      body: { new_id: 'mine', as_version: false },
    });
  });

  it('refuses an invalid copy name', async () => {
    setup('momentum_12_1');
    await userEvent.click(screen.getByRole('button', { name: 'Clone' }));
    await userEvent.type(screen.getByRole('textbox', { name: 'Name of your copy' }), 'X');
    expect(screen.getByText('Use 1-64 of a-z, 0-9, _ and -.')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Clone' }).at(-1)).toBeDisabled();
  });

  it('follows with the server warning when the verdict is not good', async () => {
    PUT.mockResolvedValue(ok({ edge_id: 'earnings_drift', state: 'following' }));
    setup('earnings_drift');
    await userEvent.click(screen.getByRole('button', { name: 'Follow' }));
    expect(screen.getByText(/win rate above the base rate is 49%/)).toBeInTheDocument();
    await userEvent.click(screen.getAllByRole('button', { name: 'Follow' }).at(-1) as HTMLElement);
    await waitFor(() => {
      expect(PUT).toHaveBeenCalledWith('/edges/{edge_id}/state', {
        params: { path: { edge_id: 'earnings_drift' } },
        body: { state: 'following', reason: '', reveal_oos: false },
      });
    });
  });

  it('needs a reason to reject', async () => {
    PUT.mockResolvedValue(ok({ edge_id: 'momentum_12_1', state: 'rejected' }));
    setup('momentum_12_1');
    await userEvent.click(screen.getByRole('button', { name: 'Reject' }));
    const confirm = () => screen.getAllByRole('button', { name: 'Reject' }).at(-1) as HTMLElement;
    expect(confirm()).toBeDisabled();
    await userEvent.type(screen.getByRole('textbox', { name: 'Why' }), 'No edge.');
    await userEvent.click(confirm());
    await waitFor(() => {
      expect(PUT).toHaveBeenCalledWith('/edges/{edge_id}/state', {
        params: { path: { edge_id: 'momentum_12_1' } },
        body: { state: 'rejected', reason: 'No edge.', reveal_oos: false },
      });
    });
  });

  it('shows the hidden out-of-sample result without changing the state', async () => {
    PUT.mockResolvedValue(ok({ edge_id: 'my_momentum', state: 'researching' }));
    setup('my_momentum');
    await userEvent.click(screen.getByRole('button', { name: 'Show out-of-sample' }));
    await userEvent.click(
      screen.getAllByRole('button', { name: 'Show out-of-sample' }).at(-1) as HTMLElement,
    );
    await waitFor(() => {
      expect(PUT).toHaveBeenCalledWith('/edges/{edge_id}/state', {
        params: { path: { edge_id: 'my_momentum' } },
        body: { state: null, reason: '', reveal_oos: true },
      });
    });
  });

  it('offers Publish site-wide to an admin on a copy only', () => {
    viewer.role = 'admin';
    const { unmount } = setup('my_momentum');
    expect(buttons()).toContain('Publish site-wide');
    unmount();
    setup('momentum_12_1');
    expect(buttons()).not.toContain('Publish site-wide');
  });
});
