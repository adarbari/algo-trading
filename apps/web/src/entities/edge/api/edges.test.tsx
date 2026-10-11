import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { gql } from '@/shared/api';

import { EDGES_FIXTURE, TRACK_RECORDS_FIXTURE } from '../model/fixtures';
import { useEdgeProblems, useEdges } from './edges';
import { useEdgeLiveStates } from './paper';
import { useTrackRecords } from './track-records';

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

describe('useEdges', () => {
  it('asks the EdgesPage operation and serves the edges with their verdicts', async () => {
    GQL.mockResolvedValue(EDGES_FIXTURE);
    const { result } = renderHook(() => useEdges(), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(String(GQL.mock.calls[0]?.[0])).toContain('query EdgesPage');
    expect(result.current.data?.[0]?.verdict.verdict).toBe('promising');
  });
});

describe('useEdgeProblems', () => {
  it('serves the files that did not load from the same read', async () => {
    GQL.mockResolvedValue(EDGES_FIXTURE);
    const { result } = renderHook(() => useEdgeProblems(), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data?.map((p) => p.edgeId)).toEqual(['broken']);
  });
});

describe('useTrackRecords', () => {
  it('asks ScreenerTrackRecords once and selects one screener, with its edge status', async () => {
    GQL.mockResolvedValue(TRACK_RECORDS_FIXTURE);
    const { result } = renderHook(() => useTrackRecords('momentum_12_1'), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(String(GQL.mock.calls[0]?.[0])).toContain('query ScreenerTrackRecords');
    expect(result.current.data?.map((r) => [r.edgeId, r.edgeStatus])).toEqual([
      ['momentum_12_1', 'candidate'],
      ['earnings_drift', 'evidenced'],
    ]);
  });
});

describe('useEdgeLiveStates', () => {
  it('reads the desk document once and serves the states, none when nothing is stored', async () => {
    const live = {
      edgeId: 'drift',
      name: 'Drift',
      state: 'below',
      closed: 20,
      winRate: 0.2,
      headline: '4 of 20 closed trades won.',
      followed: false,
    };
    GQL.mockResolvedValueOnce({ edgeDesk: { liveStates: [live] } });
    const { result } = renderHook(() => useEdgeLiveStates(), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(String(GQL.mock.calls[0]?.[0])).toContain('liveStates {');
    expect(result.current.data).toEqual([live]);
    GQL.mockResolvedValueOnce({ edgeDesk: null });
    const empty = renderHook(() => useEdgeLiveStates(), { wrapper });
    await waitFor(() => {
      expect(empty.result.current.isSuccess).toBe(true);
    });
    expect(empty.result.current.data).toEqual([]);
  });
});
