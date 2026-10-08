import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { gql, GraphQLRequestError } from '@/shared/api';

import { IDEA_FEATURES } from '../model/facts';
import { IDEAS_LIMIT, useIdeas } from './hooks';

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

describe('useIdeas', () => {
  it('asks the IdeasPage operation for the ideas and their facts, and shapes it', async () => {
    GQL.mockResolvedValue({
      ideas: {
        session: '2026-10-02',
        priority: ['vrp'],
        total: 0,
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
    expect(variables).toEqual({ limit: IDEAS_LIMIT, names: IDEA_FEATURES });
    expect(result.current.data?.screeners.map((s) => [s.id, s.notRun?.kind])).toEqual([
      ['vrp', 'NOT_RUN'],
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
