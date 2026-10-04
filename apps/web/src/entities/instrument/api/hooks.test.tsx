import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { api } from '@/shared/api';

import { useFeatureHistory, useInstrument, useInstrumentBars, useInstrumentEvents } from './hooks';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, api: { GET: vi.fn() } };
});

const GET = vi.mocked(api.GET);

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe('instrument hooks', () => {
  it('read the detail, bars, events and history of one ticker', async () => {
    GET.mockResolvedValue({ data: {}, response: new Response() });
    const hooks = renderHook(
      () => [
        useInstrument('AAPL'),
        useInstrumentBars('AAPL', '2025-10-02'),
        useInstrumentEvents('AAPL'),
        useFeatureHistory('AAPL', '2026-07-04'),
      ],
      { wrapper },
    );
    await waitFor(() => {
      expect(hooks.result.current.every((q) => q.isSuccess)).toBe(true);
    });
    const path = { instrument_id: 'AAPL' };
    expect(GET).toHaveBeenCalledWith('/instruments/{instrument_id}', { params: { path } });
    expect(GET).toHaveBeenCalledWith('/instruments/{instrument_id}/bars', {
      params: { path, query: { from: '2025-10-02' } },
    });
    expect(GET).toHaveBeenCalledWith('/instruments/{instrument_id}/events', { params: { path } });
    expect(GET).toHaveBeenCalledWith('/instruments/{instrument_id}/features', {
      params: { path, query: { from: '2026-07-04' } },
    });
  });

  it('read nothing without a ticker', () => {
    GET.mockClear();
    const { result } = renderHook(() => useInstrument(null), { wrapper });
    expect(result.current.fetchStatus).toBe('idle');
    expect(GET).not.toHaveBeenCalled();
  });
});
