import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { api } from '@/shared/api';

import { useEtfHoldings } from './hooks';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, api: { GET: vi.fn() } };
});

const GET = vi.mocked(api.GET);

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe('useEtfHoldings', () => {
  it('reads the top holdings of one ticker', async () => {
    GET.mockResolvedValue({ data: { items: [] }, response: new Response() });
    const { result } = renderHook(() => useEtfHoldings('SPY', 10), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(GET).toHaveBeenCalledWith('/instruments/{instrument_id}/holdings', {
      params: { path: { instrument_id: 'SPY' }, query: { top: 10 } },
    });
  });

  it('reads nothing without a ticker', () => {
    GET.mockClear();
    const { result } = renderHook(() => useEtfHoldings(null, 10), { wrapper });
    expect(result.current.fetchStatus).toBe('idle');
    expect(GET).not.toHaveBeenCalled();
  });
});
