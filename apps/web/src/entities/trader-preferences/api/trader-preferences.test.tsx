import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { api, gql } from '@/shared/api';

import { useSaveIdeasTab, useSaveWatchlist, useTraderPreferences } from './trader-preferences';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, gql: vi.fn(), api: { PUT: vi.fn() } };
});

const GQL = vi.mocked(gql);
const PUT = vi.mocked(api.PUT);

afterEach(() => {
  vi.clearAllMocks();
});

const answer = (defaultTab: string | null, ids: string[] = []) => ({
  traderPreferences: {
    defaultTab,
    watchlist: ids.map((instrumentId) => ({ instrumentId, symbol: instrumentId.slice(3) })),
  },
});

function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { wrapper };
}

describe('the stored choices', () => {
  it('read the tab and the watchlist; an unknown tab reads as not answered', async () => {
    GQL.mockResolvedValue(answer('premium', ['EQ:AAA']));
    const { wrapper } = setup();
    const { result } = renderHook(() => useTraderPreferences(), { wrapper });
    await waitFor(() => {
      expect(result.current.data?.defaultTab).toBe('premium');
    });
    expect(result.current.data?.watchlist).toEqual([{ instrumentId: 'EQ:AAA', symbol: 'AAA' }]);
    expect(String(GQL.mock.calls[0]?.[0])).toContain('query TraderPreferences');
    GQL.mockResolvedValue(answer('yours'));
    const other = renderHook(() => useTraderPreferences(), { wrapper: setup().wrapper });
    await waitFor(() => {
      expect(other.result.current.data?.defaultTab).toBeNull();
    });
  });

  it('save the tab through PUT /preferences/ideas, shown at once', async () => {
    GQL.mockResolvedValue(answer(null));
    PUT.mockResolvedValue({ data: { default_tab: 'stocks' }, response: new Response() });
    const { wrapper } = setup();
    const read = renderHook(() => useTraderPreferences(), { wrapper });
    await waitFor(() => {
      expect(read.result.current.data).toBeDefined();
    });
    const save = renderHook(() => useSaveIdeasTab(), { wrapper });
    await act(async () => {
      await save.result.current.mutateAsync('stocks');
    });
    expect(PUT).toHaveBeenCalledWith('/preferences/ideas', { body: { default_tab: 'stocks' } });
  });

  it('save the watchlist as instrument ids and put it back when the write fails', async () => {
    GQL.mockResolvedValue(answer('stocks', ['EQ:AAA']));
    PUT.mockRejectedValue(new Error('no'));
    const { wrapper } = setup();
    const read = renderHook(() => useTraderPreferences(), { wrapper });
    await waitFor(() => {
      expect(read.result.current.data?.watchlist).toHaveLength(1);
    });
    const save = renderHook(() => useSaveWatchlist(), { wrapper });
    await act(async () => {
      await save.result.current.mutateAsync([]).catch(() => undefined);
    });
    expect(PUT).toHaveBeenCalledWith('/preferences/watchlist', { body: { instruments: [] } });
    await waitFor(() => {
      expect(read.result.current.data?.watchlist).toHaveLength(1);
    });
  });
});
