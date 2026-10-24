import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { gql } from '@/shared/api';

import { SUMMARIES_FIXTURE, record } from '../model/fixtures';
import { useScreenerRun, useScreenerRuns } from './screener-runs';

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

describe('screener run hooks', () => {
  it('asks AdminScreenerRuns for the runs and sends the filters to the server', async () => {
    GQL.mockResolvedValue({ screenerRuns: SUMMARIES_FIXTURE });
    const { result } = renderHook(() => useScreenerRuns({ user: 'abhi', status: 'failed' }), {
      wrapper,
    });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(String(GQL.mock.calls[0]?.[0])).toContain('query AdminScreenerRuns');
    expect(GQL.mock.calls[0]?.[1]).toEqual({
      limit: 100,
      user: 'abhi',
      screener: null,
      status: 'failed',
    });
    expect(result.current.data).toHaveLength(2);
  });

  it('asks AdminScreenerRun for one run only once a run is chosen', async () => {
    GQL.mockResolvedValue({ screenerRun: record() });
    const idle = renderHook(() => useScreenerRun(null), { wrapper });
    expect(idle.result.current.fetchStatus).toBe('idle');
    expect(GQL).not.toHaveBeenCalled();
    const { result } = renderHook(() => useScreenerRun('screen-trend-site-1'), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(String(GQL.mock.calls[0]?.[0])).toContain('query AdminScreenerRun(');
    expect(result.current.data?.configVersion).toBe(3);
  });
});
