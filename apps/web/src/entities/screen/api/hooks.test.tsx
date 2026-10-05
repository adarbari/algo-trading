import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { api, gql } from '@/shared/api';

import {
  forgetScreen,
  PREVIEW_ROWS,
  refreshScreens,
  useMyScreeners,
  useScreener,
  useScreenerVersions,
  useScreenPreview,
  useScreeners,
} from './hooks';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, api: { GET: vi.fn(), POST: vi.fn() }, gql: vi.fn() };
});

const GET = vi.mocked(api.GET);
const POST = vi.mocked(api.POST);
const GQL = vi.mocked(gql);
/** The text of the `n`th GraphQL operation sent. */
const operation = (n: number) => String(GQL.mock.calls[n]?.[0]);
const ok = <T,>(data: T) => ({ data, response: new Response(null, { status: 200 }) });

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  GET.mockReset();
  POST.mockReset();
  GQL.mockReset();
});

describe('useScreeners', () => {
  it('reads the screener configs over GraphQL', async () => {
    GQL.mockResolvedValue({ configs: [{ configId: 'a', kind: 'screener' }] });
    const { result } = renderHook(() => useScreeners(), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data?.map((c) => c.configId)).toEqual(['a']);
    expect(operation(0)).toContain('configs(kind: "screener")');
  });
});

describe('useMyScreeners', () => {
  it('reads myScreens: finalized and draft-only screens', async () => {
    GQL.mockResolvedValue({ myScreens: [{ screenerId: 'a', status: 'DRAFT' }] });
    const { result } = renderHook(() => useMyScreeners(), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data?.[0]?.status).toBe('DRAFT');
    expect(operation(0)).toContain('query MyScreens');
  });
});

describe('useScreener and its versions', () => {
  it('reads one screen by id (null: no such screen), and nothing without one', async () => {
    GQL.mockResolvedValue({ screenDetail: null });
    const { result } = renderHook(() => useScreener('my'), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data).toBeNull();
    expect(operation(0)).toContain('query ScreenDetail');
    expect(GQL.mock.calls[0]?.[1]).toEqual({ id: 'my' });
    const idle = renderHook(() => useScreener(null), { wrapper });
    expect(idle.result.current.fetchStatus).toBe('idle');
  });

  it('reads the versions only when asked', async () => {
    GQL.mockResolvedValue({ screenVersions: [{ version: 1, document: { id: 'my' } }] });
    const off = renderHook(() => useScreenerVersions('my', false), { wrapper });
    expect(off.result.current.fetchStatus).toBe('idle');
    const on = renderHook(() => useScreenerVersions('my'), { wrapper });
    await waitFor(() => {
      expect(on.result.current.isSuccess).toBe(true);
    });
    expect(on.result.current.data).toEqual([{ version: 1, document: { id: 'my' } }]);
  });
});

describe('refreshScreens and forgetScreen', () => {
  it('reads every screen operation again and drops one detail', async () => {
    const client = new QueryClient();
    const invalidate = vi.spyOn(client, 'invalidateQueries');
    const remove = vi.spyOn(client, 'removeQueries');
    await refreshScreens(client);
    expect(invalidate.mock.calls.map(([filters]) => filters?.queryKey)).toEqual([
      ['gql', 'ScreenerConfigs'],
      ['gql', 'MyScreens'],
      ['gql', 'ScreenDetail'],
      ['gql', 'ScreenVersions'],
    ]);
    forgetScreen(client, 'my');
    expect(remove).toHaveBeenCalledWith({ queryKey: ['gql', 'ScreenDetail', { id: 'my' }] });
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
