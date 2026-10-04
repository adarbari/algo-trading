import { ToastProvider } from '@algotrade/ui';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { api, TestQueryProvider } from '@/shared/api';
import { expectNoA11yViolations } from '@/shared/lib/testing';

import { FinaliseButton } from './FinaliseButton';
import { RebaseBanner } from './RebaseBanner';
import { ScheduleToggle } from './ScheduleToggle';

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

describe('ScheduleToggle', () => {
  it('switches the nightly schedule apart from finalising', async () => {
    PUT.mockResolvedValue(ok({ screener_id: 'my', schedule: 'nightly' }) as never);
    const { container } = wrap(<ScheduleToggle screenerId="my" schedule={null} finalised />);
    await expectNoA11yViolations(container);
    await userEvent.click(screen.getByRole('checkbox', { name: 'Run nightly' }));
    await waitFor(() => {
      expect(PUT).toHaveBeenCalledWith('/screeners/{screener_id}/schedule', {
        params: { path: { screener_id: 'my' } },
        body: { schedule: 'nightly' },
      });
    });
    expect(POST).not.toHaveBeenCalled();
  });

  it('switches it off', async () => {
    PUT.mockResolvedValue(ok({ screener_id: 'my', schedule: null }) as never);
    wrap(<ScheduleToggle screenerId="my" schedule="nightly" finalised />);
    await userEvent.click(screen.getByRole('checkbox', { name: 'Run nightly' }));
    await waitFor(() => {
      expect(PUT).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({ body: { schedule: null } }),
      );
    });
  });

  it('waits for a finalised version', () => {
    wrap(<ScheduleToggle screenerId="my" schedule={null} finalised={false} />);
    expect(screen.getByRole('checkbox', { name: 'Run nightly' })).toBeDisabled();
    expect(screen.getByText('Finalize a version first')).toBeInTheDocument();
  });

  it('says so when the schedule could not change', async () => {
    PUT.mockResolvedValue(fail('finalise a version before scheduling') as never);
    wrap(<ScheduleToggle screenerId="my" schedule={null} finalised />);
    await userEvent.click(screen.getByRole('checkbox', { name: 'Run nightly' }));
    expect(await screen.findByText('Could not change the schedule')).toBeInTheDocument();
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
