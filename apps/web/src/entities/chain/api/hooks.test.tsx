import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { api } from '@/shared/api';

import { useOptionChain } from './hooks';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, api: { GET: vi.fn() } };
});

const GET = vi.mocked(api.GET);

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe('option chain hook', () => {
  it('reads one expiry, or the whole chain without one', async () => {
    GET.mockResolvedValue({ data: { quotes: [] }, response: new Response() });
    const one = renderHook(() => useOptionChain('AAPL', '2026-11-20'), { wrapper });
    const all = renderHook(() => useOptionChain('AAPL', null), { wrapper });
    await waitFor(() => {
      expect(one.result.current.isSuccess && all.result.current.isSuccess).toBe(true);
    });
    const path = { underlying_id: 'AAPL' };
    expect(GET).toHaveBeenCalledWith('/chains/{underlying_id}', {
      params: { path, query: { expiry: '2026-11-20' } },
    });
    expect(GET).toHaveBeenCalledWith('/chains/{underlying_id}', {
      params: { path, query: { expiry: null } },
    });
  });

  it('waits while there is no ticker', () => {
    const { result } = renderHook(() => useOptionChain(null, null), { wrapper });
    expect(result.current.fetchStatus).toBe('idle');
  });
});
