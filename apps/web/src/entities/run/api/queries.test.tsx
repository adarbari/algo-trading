import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { gql, GraphQLRequestError } from '@/shared/api';

import { useNightlyRuns, useQualityChecks, useRun, useRunItems } from './queries';

vi.mock('@/shared/api', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  gql: vi.fn(),
}));

const GQL = vi.mocked(gql);

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

/** The operation name and variables of the `n`th call. */
function call(n: number): [string, unknown] {
  const [document, variables] = GQL.mock.calls[n] ?? [];
  return [/query (\w+)/.exec(String(document))?.[1] ?? '', variables];
}

describe('run queries', () => {
  beforeEach(() => {
    GQL.mockReset();
  });

  it('reads the recent nightly runs with a limit', async () => {
    GQL.mockResolvedValue({ nightlyRuns: [{ runId: 'n1' }] });
    const { result } = renderHook(() => useNightlyRuns(5), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(call(0)).toEqual(['NightlyRuns', { limit: 5 }]);
    expect(result.current.data).toEqual([{ runId: 'n1' }]);
  });

  it('reads one run and its items only when there is an id', async () => {
    GQL.mockResolvedValue({
      run: { runId: 'r1', itemsByStatus: { OK: 2, odd: 'x' }, stats: null },
      runItems: [{ key: 'AAA', code: 'OK', status: 'OK' }],
    });
    const { result: none } = renderHook(() => useRun(null), { wrapper });
    expect(none.current.fetchStatus).toBe('idle');
    const { result } = renderHook(() => useRun('r1'), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(call(0)).toEqual(['RunRecord', { runId: 'r1' }]);
    expect(result.current.data).toMatchObject({ itemsByStatus: { OK: 2 }, stats: {} });
    const { result: items } = renderHook(() => useRunItems('r1'), { wrapper });
    await waitFor(() => {
      expect(items.current.isSuccess).toBe(true);
    });
    expect(call(1)).toEqual(['RunItems', { runId: 'r1' }]);
    const { result: off } = renderHook(() => useRunItems('r1', false), { wrapper });
    expect(off.current.fetchStatus).toBe('idle');
  });

  it('reads no such run as null, and its items as a failure', async () => {
    GQL.mockResolvedValue({ run: null, runItems: null });
    const { result } = renderHook(() => useRun('nope'), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data).toBeNull();
    const { result: items } = renderHook(() => useRunItems('nope'), { wrapper });
    await waitFor(() => {
      expect(items.current.isError).toBe(true);
    });
  });

  it('reads the session quality checks and surfaces GraphQL errors', async () => {
    GQL.mockRejectedValue(new GraphQLRequestError([{ message: 'boom' }]));
    const { result } = renderHook(() => useQualityChecks(), { wrapper });
    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(call(0)[0]).toBe('QualityChecks');
    expect(result.current.error?.message).toBe('boom');
  });
});
