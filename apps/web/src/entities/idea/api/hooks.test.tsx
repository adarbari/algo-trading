import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { gql, GraphQLRequestError, queryKeys } from '@/shared/api';

import { IDEA_FEATURES } from '../model/facts';
import { IDEAS_OPERATION, IDEAS_PAGE, useIdeas } from './hooks';

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

const item = (rank: number) => ({
  rank,
  instrumentId: `EQ:${rank}`,
  regime: null,
  sizeMultiplier: null,
  instrument: { symbol: `S${rank}`, name: null, features: [] },
  picks: [
    {
      configId: 'vrp',
      decision: 'QUALIFIED',
      score: 1,
      reasons: '',
      flags: [],
      criteria: [],
      columns: [],
    },
  ],
});

const page = (ranks: number[], nextCursor: string | null) => ({
  ideas: {
    session: '2026-10-02',
    priority: [],
    total: 3,
    hasMore: nextCursor !== null,
    nextCursor,
    pausedTotal: 0,
    paused: [],
    screeners: [],
    items: ranks.map(item),
  },
});

/** A client kept across renders, so a test can seed and refetch its cache. */
function held() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrap = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { client, wrap };
}

const pageKey = (after?: string) =>
  queryKeys.gql(IDEAS_OPERATION, {
    first: IDEAS_PAGE,
    names: [...IDEA_FEATURES],
    ...(after === undefined ? {} : { after }),
  });
const asked = () => GQL.mock.calls.map((call) => (call[1] as { after: string | null }).after);

describe('useIdeas pages link up', () => {
  it('drops a second page a refreshed first page no longer leads to', async () => {
    const { client, wrap } = held();
    GQL.mockResolvedValueOnce(page([1, 2], 'c2')).mockResolvedValueOnce(page([3], null));
    const { result } = renderHook(() => useIdeas(), { wrapper: wrap });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    await result.current.fetchNextPage();
    await waitFor(() => {
      expect(result.current.data?.ideas.map((i) => i.rank)).toEqual([1, 2, 3]);
    });
    GQL.mockResolvedValueOnce(page([1, 2], 'c9')); // the runs changed: page one now leads on to c9
    await client.refetchQueries({ queryKey: pageKey(), exact: true });
    await waitFor(() => {
      expect(result.current.data?.ideas.map((i) => i.rank)).toEqual([1, 2]);
    });
    expect(result.current.hasNextPage).toBe(true);
    expect(asked()).toEqual([null, 'c2', null]); // the old second page is not asked for again
  });

  it('shows no page after one that has no data, so the list has no gap', async () => {
    const { client, wrap } = held();
    client.setQueryData(pageKey(), page([1, 2], 'c2'), { updatedAt: 1 });
    client.setQueryData(pageKey('c3'), page([5, 6], null), { updatedAt: 1 });
    client.setQueryData(['ideas-more'], ['c2', 'c3']);
    GQL.mockImplementation((_doc, variables) => {
      const after = (variables as { after: string | null }).after;
      if (after === 'c2') return Promise.reject(new GraphQLRequestError([{ message: 'boom' }]));
      return Promise.resolve(after === 'c3' ? page([5, 6], null) : page([1, 2], 'c2'));
    });
    const { result } = renderHook(() => useIdeas(), { wrapper: wrap });
    await waitFor(() => {
      expect(result.current.isFetchNextPageError).toBe(true);
    });
    expect(result.current.data?.ideas.map((i) => i.rank)).toEqual([1, 2]);
    await waitFor(() => {
      expect(client.getQueryData(['ideas-more'])).toEqual(['c2']);
    });
  });
});

describe('useIdeas', () => {
  it('appends the next page with the server cursor, in order and without a repeat', async () => {
    GQL.mockResolvedValueOnce(page([1, 2], 'c2')).mockResolvedValueOnce(page([3], null));
    const { result } = renderHook(() => useIdeas(), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data?.hasMore).toBe(true);
    await result.current.fetchNextPage();
    await waitFor(() => {
      expect(result.current.data?.ideas.map((i) => i.rank)).toEqual([1, 2, 3]);
    });
    expect(GQL.mock.calls.map((call) => (call[1] as { after: string | null }).after)).toEqual([
      null,
      'c2',
    ]);
    expect(result.current.data?.hasMore).toBe(false);
    expect(result.current.hasNextPage).toBe(false);
  });

  it('asks the IdeasPage operation for the ideas and their facts, and shapes it', async () => {
    GQL.mockResolvedValue({
      ideas: {
        session: '2026-10-02',
        priority: ['vrp'],
        total: 0,
        hasMore: false,
        nextCursor: null,
        pausedTotal: 0,
        paused: [],
        screeners: [
          {
            screener: { id: 'vrp', name: 'VRP scanner', owner: 'abhinav', version: 1 },
            run: null,
            notRun: {
              code: 'NOT_RUN',
              kind: 'NOT_RUN',
              guideTerm: 'not_run',
              kindText: 'not run for this session',
              reason: null,
              cause: null,
            },
            picked: 0,
            top: [],
          },
        ],
        items: [],
      },
    });
    const { result } = renderHook(() => useIdeas(), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    const [document, variables] = GQL.mock.calls[0] ?? [];
    expect(String(document)).toContain('query IdeasPage');
    expect(variables).toEqual({ first: IDEAS_PAGE, after: null, names: IDEA_FEATURES });
    expect(result.current.data?.screeners.map((s) => [s.id, s.notRun?.kind])).toEqual([
      ['vrp', 'NOT_RUN'],
    ]);
  });

  it('starts over from a fresh first page when the server refuses the cursor', async () => {
    GQL.mockResolvedValueOnce(page([1, 2], 'old'))
      .mockRejectedValueOnce(
        new GraphQLRequestError([{ message: 'changed', extensions: { code: 'BAD_REQUEST' } }]),
      )
      .mockResolvedValueOnce(page([7, 8], null));
    const { result } = renderHook(() => useIdeas(), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    await result.current.fetchNextPage();
    await waitFor(() => {
      expect(result.current.data?.ideas.map((i) => i.rank)).toEqual([7, 8]);
    });
    expect(GQL.mock.calls.map((call) => (call[1] as { after: string | null }).after)).toEqual([
      null,
      'old',
      null,
    ]);
  });

  it('surfaces a GraphQL error', async () => {
    GQL.mockRejectedValue(new GraphQLRequestError([{ message: 'boom' }]));
    const { result } = renderHook(() => useIdeas(), { wrapper });
    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(result.current.error).toMatchObject({ codes: ['INTERNAL'] });
  });
});
