import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { api } from '@/shared/api';

import {
  PREVIEW_ROWS,
  useScreener,
  useScreenerVersions,
  useScreenPreview,
  useScreeners,
} from './hooks';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, api: { GET: vi.fn(), POST: vi.fn() } };
});

const GET = vi.mocked(api.GET);
const POST = vi.mocked(api.POST);
const ok = <T,>(data: T) => ({ data, response: new Response(null, { status: 200 }) });

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  GET.mockReset();
  POST.mockReset();
});

describe('useScreeners', () => {
  it('keeps the screeners of GET /configs', async () => {
    GET.mockResolvedValue(
      ok([
        { config_id: 'a', kind: 'screener' },
        { config_id: 's', kind: 'strategy' },
      ]),
    );
    const { result } = renderHook(() => useScreeners(), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data?.map((c) => c.config_id)).toEqual(['a']);
    expect(GET).toHaveBeenCalledWith('/configs');
  });
});

describe('useScreener and its versions', () => {
  it('reads one screen by id, and nothing without one', async () => {
    GET.mockResolvedValue(ok({ screener_id: 'my' }));
    const { result } = renderHook(() => useScreener('my'), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(GET).toHaveBeenCalledWith('/screeners/{screener_id}', {
      params: { path: { screener_id: 'my' } },
    });
    const idle = renderHook(() => useScreener(null), { wrapper });
    expect(idle.result.current.fetchStatus).toBe('idle');
  });

  it('reads the versions only when asked', async () => {
    GET.mockResolvedValue(ok([]));
    const off = renderHook(() => useScreenerVersions('my', false), { wrapper });
    expect(off.result.current.fetchStatus).toBe('idle');
    const on = renderHook(() => useScreenerVersions('my'), { wrapper });
    await waitFor(() => {
      expect(on.result.current.isSuccess).toBe(true);
    });
  });
});

describe('useScreenPreview', () => {
  it('posts the draft with the row limit and does nothing without one', async () => {
    POST.mockResolvedValue(ok({ rows: [] }));
    const { result } = renderHook(() => useScreenPreview({ id: 'my', criteria: {} }), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(POST).toHaveBeenCalledWith('/screeners/preview', {
      body: { spec: { id: 'my', criteria: {} }, limit: PREVIEW_ROWS },
    });
    const idle = renderHook(() => useScreenPreview(null), { wrapper });
    expect(idle.result.current.fetchStatus).toBe('idle');
  });

  it('surfaces the API message naming the criterion', async () => {
    POST.mockResolvedValue({
      error: { detail: 'my.criteria.a.field: bad' },
      response: new Response(null, { status: 400 }),
    });
    const { result } = renderHook(() => useScreenPreview({ id: 'my' }), { wrapper });
    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(result.current.error?.message).toContain('my.criteria.a.field');
  });
});
