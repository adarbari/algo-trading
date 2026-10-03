import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { api } from '@/shared/api';

import { useNightlyRuns, useQualityChecks, useRun, useRunItems } from './queries';

vi.mock('@/shared/api', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  api: { GET: vi.fn() },
}));

const GET = vi.mocked(api.GET);
const ok = (data: unknown) =>
  Promise.resolve({ data, response: new Response(null, { status: 200 }) }) as never;

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe('run queries', () => {
  beforeEach(() => {
    GET.mockReset();
  });

  it('reads the recent nightly runs with a limit', async () => {
    GET.mockReturnValue(ok([{ run_id: 'n1' }]));
    const { result } = renderHook(() => useNightlyRuns(5), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(GET).toHaveBeenCalledWith('/admin/runs/nightly', { params: { query: { limit: 5 } } });
    expect(result.current.data).toEqual([{ run_id: 'n1' }]);
  });

  it('reads one run and its items only when there is an id', async () => {
    GET.mockReturnValue(ok({ run_id: 'r1' }));
    const { result: none } = renderHook(() => useRun(null), { wrapper });
    expect(none.current.fetchStatus).toBe('idle');
    const { result } = renderHook(() => useRun('r1'), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(GET).toHaveBeenCalledWith('/admin/runs/{run_id}', {
      params: { path: { run_id: 'r1' } },
    });
    const { result: items } = renderHook(() => useRunItems('r1'), { wrapper });
    await waitFor(() => {
      expect(items.current.isSuccess).toBe(true);
    });
    expect(GET).toHaveBeenCalledWith('/admin/runs/{run_id}/items', {
      params: { path: { run_id: 'r1' } },
    });
    const { result: off } = renderHook(() => useRunItems('r1', false), { wrapper });
    expect(off.current.fetchStatus).toBe('idle');
  });

  it('surfaces API errors', async () => {
    GET.mockReturnValue(
      Promise.resolve({
        error: { detail: 'no data-quality run' },
        response: new Response(null, { status: 404 }),
      }),
    );
    const { result } = renderHook(() => useQualityChecks(), { wrapper });
    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(result.current.error?.message).toBe('API 404: no data-quality run');
  });
});
