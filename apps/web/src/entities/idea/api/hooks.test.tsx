import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { api } from '@/shared/api';

import { IDEAS_LIMIT, useIdeas } from './hooks';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, api: { GET: vi.fn() } };
});

const GET = vi.mocked(api.GET);

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  GET.mockReset();
});

describe('useIdeas', () => {
  it('fetches /ideas and shapes it', async () => {
    GET.mockResolvedValue({
      data: { session: '2026-10-02', priority: ['vrp'], total: 0, items: [] },
      response: new Response(null, { status: 200 }),
    });
    const { result } = renderHook(() => useIdeas(), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(GET).toHaveBeenCalledWith('/ideas', { params: { query: { limit: IDEAS_LIMIT } } });
    expect(result.current.data?.screeners.map((s) => s.id)).toEqual(['vrp']);
  });

  it('surfaces an API error', async () => {
    GET.mockResolvedValue({
      error: { detail: 'no session' },
      response: new Response(null, { status: 404 }),
    });
    const { result } = renderHook(() => useIdeas(), { wrapper });
    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(result.current.error).toMatchObject({ status: 404 });
  });
});
