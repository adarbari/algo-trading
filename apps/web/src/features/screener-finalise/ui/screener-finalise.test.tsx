import { ToastProvider } from '@algotrade/ui';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { api, TestQueryProvider } from '@/shared/api';
import { expectNoA11yViolations } from '@/shared/lib/testing';

import { FinaliseButton } from './FinaliseButton';
import { RebaseBanner } from './RebaseBanner';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, api: { POST: vi.fn(), PUT: vi.fn() } };
});

const POST = vi.mocked(api.POST);
const PUT = vi.mocked(api.PUT);
const ok = (data: unknown) => ({ data, response: new Response(null, { status: 200 }) });
const fail = (detail: string) => ({
  error: { detail },
  response: new Response(null, { status: 400 }),
});

const wrap = (node: React.ReactNode) =>
  render(
    <ToastProvider>
      <TestQueryProvider>{node}</TestQueryProvider>
    </ToastProvider>,
  );

beforeEach(() => {
  POST.mockReset();
  PUT.mockReset();
});

describe('FinaliseButton', () => {
  it('saves the draft first, then finalizes, and says which version it made', async () => {
    const order: string[] = [];
    POST.mockImplementation((() => {
      order.push('finalise');
      return Promise.resolve(ok({ screener_id: 'my', version: 3, hash: 'h' }));
    }) as never);
    const prepare = vi.fn(() => {
      order.push('save');
      return Promise.resolve();
    });
    const { container } = wrap(<FinaliseButton screenerId="my" version={3} prepare={prepare} />);
    await expectNoA11yViolations(container);
    await userEvent.click(screen.getByRole('button', { name: 'Finalize v3' }));
    expect(await screen.findByText('Finalised v3')).toBeInTheDocument();
    expect(order).toEqual(['save', 'finalise']);
  });

  it('does not finalize when the save fails, and says why when finalising fails', async () => {
    const { rerender } = wrap(
      <FinaliseButton
        screenerId="my"
        version={1}
        prepare={() => Promise.reject(new Error('no'))}
      />,
    );
    await userEvent.click(screen.getByRole('button', { name: 'Finalize v1' }));
    expect(POST).not.toHaveBeenCalled();
    POST.mockResolvedValue(fail('my.criteria.a.field: unknown field'));
    rerender(
      <ToastProvider>
        <TestQueryProvider>
          <FinaliseButton screenerId="my" version={1} prepare={() => Promise.resolve()} />
        </TestQueryProvider>
      </ToastProvider>,
    );
    await userEvent.click(screen.getByRole('button', { name: 'Finalize v1' }));
    expect(await screen.findByText('Could not finalise')).toBeInTheDocument();
  });

  it('is disabled when there is nothing to finalize', () => {
    wrap(<FinaliseButton screenerId="my" version={1} prepare={() => Promise.resolve()} disabled />);
    expect(screen.getByRole('button', { name: 'Finalize v1' })).toBeDisabled();
  });
});

describe('RebaseBanner', () => {
  it('offers the newer preset version and rebases', async () => {
    POST.mockResolvedValue(ok({ screener_id: 'my', document: {} }));
    const { container } = wrap(
      <RebaseBanner screenerId="my" preset="vrp" pinned={1} current={2} />,
    );
    expect(
      screen.getByText(/vrp has a newer version \(v2\); this screener is pinned to v1/),
    ).toBeInTheDocument();
    await expectNoA11yViolations(container);
    await userEvent.click(screen.getByRole('button', { name: 'Rebase on v2' }));
    await waitFor(() => {
      expect(POST).toHaveBeenCalledWith('/screeners/{screener_id}/rebase', {
        params: { path: { screener_id: 'my' } },
      });
    });
  });

  it('asks to save the draft first when there are unsaved edits', () => {
    wrap(<RebaseBanner screenerId="my" preset="vrp" pinned={1} current={2} disabled />);
    expect(screen.getByRole('button', { name: 'Rebase on v2' })).toBeDisabled();
    expect(screen.getByText(/save the draft first/)).toBeInTheDocument();
  });
});
