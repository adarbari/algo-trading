import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { gql } from '@/shared/api';

import { useEdgeTrades } from './evidence';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, gql: vi.fn() };
});

const GQL = vi.mocked(gql);

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  GQL.mockReset();
});

describe('the edge ledger reads', () => {
  it('asks the server for a sorted page of one period and passes no run, screen or horizon', async () => {
    GQL.mockResolvedValue({ edgeTrades: { total: 0, rows: [] } });
    const request = {
      edgeId: 'drift',
      period: 'OUT_OF_SAMPLE',
      page: 2,
      sort: 'VALUE',
      descending: true,
    } as const;
    const { result } = renderHook(() => useEdgeTrades(request), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(String(GQL.mock.calls[0]?.[0])).toContain('query EdgeTrades');
    expect(GQL.mock.calls[0]?.[1]).toEqual(request);
  });
});
