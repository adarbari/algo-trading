import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { gql } from '@/shared/api';

import {
  useEdgeCosts,
  useEdgeCurve,
  useEdgeDecay,
  useEdgeDrawdown,
  useEdgeHorizons,
  useEdgeRegimes,
  useEdgeResultBasis,
} from './edge-result';

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

describe('the edge result sections', () => {
  it('reads each section with its own operation and serves just that section', async () => {
    GQL.mockResolvedValue({
      edgeResult: { curve: { kind: 'cumulative_excess', points: [], gaps: [], live: null } },
    });
    const { result } = renderHook(() => useEdgeCurve('drift', '2026-10-05'), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(String(GQL.mock.calls[0]?.[0])).toContain('query EdgeResultCurve');
    expect(GQL.mock.calls[0]?.[1]).toEqual({ id: 'drift', date: '2026-10-05' });
    expect(result.current.data?.kind).toBe('cumulative_excess');
  });

  it('asks only for the session the live parts need, and none of the others', async () => {
    GQL.mockResolvedValue({ edgeResult: { drawdown: { unit: 'excess_return' } } });
    const { result } = renderHook(() => useEdgeDrawdown('drift'), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(String(GQL.mock.calls[0]?.[0])).toContain('query EdgeResultDrawdown');
    expect(GQL.mock.calls[0]?.[1]).toEqual({ id: 'drift' });
  });

  it('serves null for an edge the user does not have', async () => {
    GQL.mockResolvedValue({ edgeResult: null });
    const basis = renderHook(() => useEdgeResultBasis('nope'), { wrapper });
    const decay = renderHook(() => useEdgeDecay('nope'), { wrapper });
    await waitFor(() => {
      expect(basis.result.current.isSuccess && decay.result.current.isSuccess).toBe(true);
    });
    expect(basis.result.current.data).toBeNull();
    expect(decay.result.current.data).toBeNull();
  });

  it('reads the regime, holding-period and cost sections as their own documents, no date', async () => {
    GQL.mockResolvedValue({ edgeResult: { regimes: { state: 'measured', rows: [] } } });
    const regimes = renderHook(() => useEdgeRegimes('drift'), { wrapper });
    await waitFor(() => {
      expect(regimes.result.current.isSuccess).toBe(true);
    });
    expect(String(GQL.mock.calls[0]?.[0])).toContain('query EdgeResultRegimes');
    expect(GQL.mock.calls[0]?.[1]).toEqual({ id: 'drift' });
    GQL.mockResolvedValue({ edgeResult: { horizons: { state: 'measured', rows: [] } } });
    const horizons = renderHook(() => useEdgeHorizons('drift'), { wrapper });
    GQL.mockResolvedValue({ edgeResult: { costs: { state: 'measured' } } });
    const costs = renderHook(() => useEdgeCosts('drift'), { wrapper });
    await waitFor(() => {
      expect(horizons.result.current.isSuccess && costs.result.current.isSuccess).toBe(true);
    });
    expect(String(GQL.mock.calls[1]?.[0])).toContain('query EdgeResultHorizons');
    expect(String(GQL.mock.calls[2]?.[0])).toContain('query EdgeResultCosts');
    expect(horizons.result.current.data?.state).toBe('measured');
  });
});
