import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { gql } from '@/shared/api';

import { useEdgeCompare } from './hooks';

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

describe('useEdgeCompare', () => {
  it('asks the EdgeCompare operation for the copy and serves its comparison', async () => {
    const compare = { oosHidden: true, reason: '', rows: [] };
    GQL.mockResolvedValue({ edge: { compare } });
    const { result } = renderHook(() => useEdgeCompare('mine'), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(String(GQL.mock.calls[0]?.[0])).toContain('query EdgeCompare');
    expect(GQL.mock.calls[0]?.[1]).toEqual({ id: 'mine' });
    expect(result.current.data).toEqual(compare);
  });

  it('serves none for an edge with no comparison', async () => {
    GQL.mockResolvedValue({ edge: null });
    const { result } = renderHook(() => useEdgeCompare('x'), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data).toBeNull();
  });
});
