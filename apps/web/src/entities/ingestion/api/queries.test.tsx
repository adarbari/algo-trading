import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { api } from '@/shared/api';

import { useCellDetail, useCompleteness, useFocusCell } from './queries';

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

const grid = {
  sessions: ['2026-10-02'],
  datasets: ['bars/1d'],
  last_closed: '2026-10-02',
  cells: [
    {
      dataset: 'bars/1d',
      session: '2026-10-02',
      status: 'PARTIAL',
      present: 1,
      expected: 2,
      basis: '',
      run_ids: [],
    },
  ],
};

describe('ingestion queries', () => {
  beforeEach(() => {
    GET.mockReset();
  });

  it('reads the last ten sessions of the grid', async () => {
    GET.mockReturnValue(ok(grid));
    const { result } = renderHook(() => useCompleteness(), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(GET).toHaveBeenCalledWith('/admin/ingestion/completeness', {
      params: { query: { sessions: 10 } },
    });
  });

  it('reads a cell only once one is chosen', async () => {
    GET.mockReturnValue(ok({ job: 'daily_bars' }));
    const { result: none } = renderHook(() => useCellDetail(null), { wrapper });
    expect(none.current.fetchStatus).toBe('idle');
    const cell = { dataset: 'chains/option_quotes', session: '2026-10-02' };
    const { result } = renderHook(() => useCellDetail(cell), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(GET).toHaveBeenCalledWith('/admin/ingestion/{dataset}/{session}', {
      params: { path: cell },
    });
  });

  it('focuses the selected cell, else the default one', async () => {
    GET.mockReturnValue(ok(grid));
    const chosen = { dataset: 'x', session: 'y' };
    const { result: selected } = renderHook(() => useFocusCell(chosen), { wrapper });
    expect(selected.current).toBe(chosen);
    const { result } = renderHook(() => useFocusCell(null), { wrapper });
    await waitFor(() => {
      expect(result.current).toEqual({ dataset: 'bars/1d', session: '2026-10-02' });
    });
  });
});
