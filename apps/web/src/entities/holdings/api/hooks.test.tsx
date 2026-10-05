import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { gql } from '@/shared/api';

import { useEtfHoldings } from './hooks';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, gql: vi.fn() };
});

const GQL = vi.mocked(gql);

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe('useEtfHoldings', () => {
  it('reads the top holdings of one ticker in one request', async () => {
    const fund = { instrumentId: 'EQ:SPY', isEtf: true, holdings: null };
    GQL.mockResolvedValue({ instrument: fund });
    const { result } = renderHook(() => useEtfHoldings('SPY', 10), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(GQL).toHaveBeenCalledTimes(1);
    const [document, variables] = GQL.mock.calls[0] ?? [];
    expect(String(document)).toContain('query EtfHoldings');
    expect(variables).toEqual({ key: 'SPY', top: 10 });
    expect(result.current.data).toEqual(fund);
  });

  it('reads nothing without a ticker', () => {
    GQL.mockClear();
    const { result } = renderHook(() => useEtfHoldings(null, 10), { wrapper });
    expect(result.current.fetchStatus).toBe('idle');
    expect(GQL).not.toHaveBeenCalled();
  });
});
