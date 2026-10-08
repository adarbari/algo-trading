import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { gql } from '@/shared/api';

import { RUNS_FIXTURE, row } from '../model/fixtures';
import { useHarnessRunRows, useHarnessRuns } from './harness-runs';

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

describe('harness run hooks', () => {
  it('asks HarnessRuns for the runs', async () => {
    GQL.mockResolvedValue({ harnessRuns: RUNS_FIXTURE });
    const { result } = renderHook(() => useHarnessRuns(), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(String(GQL.mock.calls[0]?.[0])).toContain('query HarnessRuns');
    expect(result.current.data).toHaveLength(2);
  });

  it('asks HarnessRun for one run only once a run is chosen', async () => {
    GQL.mockResolvedValue({ harnessRun: { runId: 'run-b', rows: [row()], lostInputs: [] } });
    const idle = renderHook(() => useHarnessRunRows(null), { wrapper });
    expect(idle.result.current.fetchStatus).toBe('idle');
    expect(GQL).not.toHaveBeenCalled();
    const { result } = renderHook(() => useHarnessRunRows('run-b'), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(String(GQL.mock.calls[0]?.[0])).toContain('query HarnessRun(');
    expect(result.current.data?.rows).toHaveLength(1);
  });
});
