import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { gql } from '@/shared/api';

import { useSystemIssues } from './use-system-issues';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, gql: vi.fn() };
});

const GQL = vi.mocked(gql);

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const SCREENS = {
  ideas: {
    session: '2026-10-08',
    screeners: [
      { screener: { id: 'a', name: 'A' }, notRun: { code: 'NOT_RUN', kindText: 'Not run' } },
    ],
  },
};
const NIGHTLY = {
  nightlyRuns: [
    {
      runId: 'r1',
      session: '2026-10-08',
      status: 'FAILED',
      problems: [],
      steps: [],
    },
  ],
};

beforeEach(() => {
  GQL.mockReset();
});

describe('useSystemIssues', () => {
  it('reads only the screeners for a trader (the nightly run is admin-only)', async () => {
    GQL.mockResolvedValue(SCREENS);
    const { result } = renderHook(() => useSystemIssues(false), { wrapper });
    await waitFor(() => {
      expect(result.current).toHaveLength(1);
    });
    expect(GQL).toHaveBeenCalledOnce();
    expect(result.current[0]?.id).toBe('screen:2026-10-08:a');
  });

  it('adds the failed nightly run for an admin, ahead of the warnings', async () => {
    GQL.mockImplementation((doc) =>
      Promise.resolve(String(doc).includes('NightlyRuns') ? NIGHTLY : SCREENS),
    );
    const { result } = renderHook(() => useSystemIssues(true), { wrapper });
    await waitFor(() => {
      expect(result.current).toHaveLength(2);
    });
    expect(result.current.map((i) => i.severity)).toEqual(['failing', 'warning']);
  });

  it('adds no issue while a read fails', async () => {
    GQL.mockRejectedValue(new Error('down'));
    const { result } = renderHook(() => useSystemIssues(true), { wrapper });
    await waitFor(() => {
      expect(GQL).toHaveBeenCalled();
    });
    expect(result.current).toEqual([]);
  });
});
