import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { gql } from '@/shared/api';

import { EDGE_ROWS_FIXTURE, EDGES_FIXTURE, TRACK_RECORDS_FIXTURE } from '../model/fixtures';
import { refreshEdges, useEdge, useEdgeDocument, useEdgeProblems, useEdges } from './edges';
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
  it('asks the list operation: the headline of each verdict, never the whole verdict, runs or definition', async () => {
    GQL.mockResolvedValue({ edgeList: EDGE_ROWS_FIXTURE });
    const { result } = renderHook(() => useEdges(), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    const document = String(GQL.mock.calls[0]?.[0]);
    expect(document).toContain('query EdgesPage');
    expect(document).toContain('summary');
    expect(document).not.toMatch(/\bverdict \{|runs|canonicalRun|definition|haircut|decay/);
    expect(result.current.data?.items[0]?.summary.verdict).toBe('promising');
  });

  it('sends the filters and the search text to the server, and none when there are none', async () => {
    GQL.mockResolvedValue({ edgeList: EDGE_ROWS_FIXTURE });
    const plain = renderHook(() => useEdges(), { wrapper });
    await waitFor(() => {
      expect(plain.result.current.isSuccess).toBe(true);
    });
    expect(GQL.mock.calls[0]?.[1]).toEqual({ filters: null, q: null });
    const applied = [{ id: 'status', values: ['rejected'], active: true }];
    const narrowed = renderHook(() => useEdges(applied, 'drift'), { wrapper });
    await waitFor(() => {
      expect(narrowed.result.current.isSuccess).toBe(true);
    });
    expect(GQL.mock.calls[1]?.[1]).toEqual({
      filters: [
        { id: 'status', values: ['rejected'], min: null, max: null, within: null, active: true },
      ],
      q: 'drift',
    });
  });
});

describe('useEdge', () => {
  it('asks the EdgeDetail operation for ONE id, with the full verdict and the runs', async () => {
    GQL.mockResolvedValue({ edges: [EDGES_FIXTURE.edges[0]] });
    const { result } = renderHook(() => useEdge('momentum_12_1'), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    const document = String(GQL.mock.calls[0]?.[0]);
    expect(document).toContain('query EdgeDetail');
    expect(document).toMatch(/verdict \{/);
    expect(document).toContain('runs {');
    expect(GQL.mock.calls[0]?.[1]).toEqual({ ids: ['momentum_12_1'] });
    expect(result.current.data?.verdict.verdict).toBe('promising');
  });

  it('serves null for an edge that is not seen, and sends nothing without an id', async () => {
    GQL.mockResolvedValue({ edges: [] });
    const { result } = renderHook(() => useEdge('nope'), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data).toBeNull();
    GQL.mockClear();
    renderHook(() => useEdge(null), { wrapper });
    expect(GQL).not.toHaveBeenCalled();
  });
});

describe('useEdgeDocument', () => {
  it('asks the EdgeDocument operation for one id: no verdict, no runs', async () => {
    GQL.mockResolvedValue({ edges: [EDGES_FIXTURE.edges[0]] });
    const { result } = renderHook(() => useEdgeDocument('drift'), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    const document = String(GQL.mock.calls[0]?.[0]);
    expect(document).toContain('query EdgeDocument');
    expect(document).not.toMatch(/verdict|runs|canonicalRun/);
    expect(GQL.mock.calls[0]?.[1]).toEqual({ ids: ['drift'] });
    expect(result.current.data?.id).toBe(EDGES_FIXTURE.edges[0]?.id);
  });

  it('sends nothing for a new edge', () => {
    renderHook(() => useEdgeDocument(null), { wrapper });
    expect(GQL).not.toHaveBeenCalled();
  });
});

describe('refreshEdges', () => {
  it('waits for the list, the one-edge and the document reads to refetch', async () => {
    const client = new QueryClient();
    const spy = vi.spyOn(client, 'invalidateQueries');
    await refreshEdges(client);
    const names = spy.mock.calls.map((c) => (c[0]?.queryKey as unknown[] | undefined)?.[1]);
    expect(names.sort()).toEqual(['EdgeDetail', 'EdgeDocument', 'EdgeProblems', 'EdgesPage']);
  });
});

describe('useEdgeProblems', () => {
  it('serves the files that did not load from their own read, not the list', async () => {
    GQL.mockResolvedValue({ edgeProblems: EDGES_FIXTURE.edgeProblems });
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
