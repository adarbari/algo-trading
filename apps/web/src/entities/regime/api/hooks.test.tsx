import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { gql, GraphQLRequestError } from '@/shared/api';

import { useRegime, useRegimeBands, useRegimeEpisodes } from './hooks';

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

describe('useRegime', () => {
  it('asks the Regime operation and serves the session regime', async () => {
    GQL.mockResolvedValue({ regime: { session: '2026-10-02', label: 'UNKNOWN', indicators: [] } });
    const { result } = renderHook(() => useRegime(), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(String(GQL.mock.calls[0]?.[0])).toContain('query Regime');
    expect(result.current.data?.label).toBe('UNKNOWN');
  });

  it('serves null when nothing is stored for the session', async () => {
    GQL.mockResolvedValue({ regime: null });
    const { result } = renderHook(() => useRegime(), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data).toBeNull();
  });

  it('surfaces a GraphQL error', async () => {
    GQL.mockRejectedValue(new GraphQLRequestError([{ message: 'boom' }]));
    const { result } = renderHook(() => useRegime(), { wrapper });
    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });
});

describe('useRegimeBands', () => {
  it('asks the RegimeBands operation for the window and serves the bands', async () => {
    GQL.mockResolvedValue({
      regime: { bands: [{ start: '2026-08-03', end: '2026-08-07', label: 'STRESS' }] },
    });
    const { result } = renderHook(() => useRegimeBands('2026-08-01', '2026-10-02'), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    const [document, variables] = GQL.mock.calls[0] ?? [];
    expect(String(document)).toContain('query RegimeBands');
    expect(variables).toEqual({ start: '2026-08-01', end: '2026-10-02' });
    expect(result.current.data).toEqual([
      { start: '2026-08-03', end: '2026-08-07', label: 'STRESS' },
    ]);
  });

  it('does not ask before the window end is known, and serves no bands for a null regime', async () => {
    const { result, rerender } = renderHook(
      ({ end }: { end: string | undefined }) => useRegimeBands('2026-08-01', end),
      { wrapper, initialProps: { end: undefined as string | undefined } },
    );
    expect(GQL).not.toHaveBeenCalled();
    GQL.mockResolvedValue({ regime: null });
    rerender({ end: '2026-10-02' });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data).toEqual([]);
  });
});

describe('useRegimeEpisodes', () => {
  it('asks the RegimeEpisodes operation and serves the episodes and recessions the session knows', async () => {
    const episode = { key: 'covid_2020', name: 'Covid crash, early 2020', recovered: '2020-08-18' };
    const recession = { start: '2020-02-01', end: null, announcedStart: '2020-06-08' };
    GQL.mockResolvedValue({ regime: { episodes: [episode], recessions: [recession] } });
    const { result } = renderHook(() => useRegimeEpisodes(), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(String(GQL.mock.calls[0]?.[0])).toContain('query RegimeEpisodes');
    expect(result.current.data).toEqual({ episodes: [episode], recessions: [recession] });
  });

  it('serves none for a null regime', async () => {
    GQL.mockResolvedValue({ regime: null });
    const { result } = renderHook(() => useRegimeEpisodes(), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data).toEqual({ episodes: [], recessions: [] });
  });
});
