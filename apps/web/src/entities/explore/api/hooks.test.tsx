import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { gql } from '@/shared/api';

import { useComparePrices } from './hooks';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, gql: vi.fn() };
});

const GQL = vi.mocked(gql);

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe('compare hooks', () => {
  it("reads the whole compare set's closes in one request", async () => {
    GQL.mockResolvedValue({
      table: {
        instruments: [
          { instrumentId: 'EQ:A', symbol: 'AAPL', prices: { bars: [{ session: 'd', close: 1 }] } },
          { instrumentId: 'EQ:M', symbol: 'MSFT', prices: { bars: [] } },
        ],
      },
    });
    const { result } = renderHook(() => useComparePrices(['AAPL', 'MSFT'], '2025-10-02'), {
      wrapper,
    });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(GQL).toHaveBeenCalledTimes(1);
    expect(String(GQL.mock.calls[0]?.[0])).toContain('query ComparePrices');
    expect(GQL.mock.calls[0]?.[1]).toEqual({ keys: ['AAPL', 'MSFT'], start: '2025-10-02' });
    expect(result.current.data).toEqual([
      { symbol: 'AAPL', instrumentId: 'EQ:A', closes: [{ session: 'd', close: 1 }] },
      { symbol: 'MSFT', instrumentId: 'EQ:M', closes: [] },
    ]);
  });

  it('asks for nothing without a compare set', () => {
    GQL.mockClear();
    renderHook(() => useComparePrices([], '2025-10-02'), { wrapper });
    expect(GQL).not.toHaveBeenCalled();
  });
});
