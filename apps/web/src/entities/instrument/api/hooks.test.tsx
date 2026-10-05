import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { gql } from '@/shared/api';

import {
  NAMES_PER_REQUEST,
  useFeatureHistory,
  useFeatureValues,
  useInstrumentEvents,
  useInstrumentPrices,
} from './hooks';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, gql: vi.fn() };
});

const GQL = vi.mocked(gql);

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

/** The operation name and variables of every gql() call so far. */
const calls = () =>
  GQL.mock.calls.map(([document, variables]) => [
    /query (\w+)/.exec(String(document))?.[1],
    variables,
  ]);

const value = (name: string) => ({ name, value: 1, unknown: null, info: { format: 'NUMBER' } });

describe('instrument hooks', () => {
  it('read the events and the bars of one ticker', async () => {
    GQL.mockResolvedValue({
      instrument: { instrumentId: 'EQ:A', events: [], prices: { bars: [{ session: 'd' }] } },
    });
    const events = renderHook(() => useInstrumentEvents('AAPL'), { wrapper });
    const prices = renderHook(() => useInstrumentPrices('AAPL', '2025-10-02'), { wrapper });
    await waitFor(() => {
      expect(events.result.current.isSuccess && prices.result.current.isSuccess).toBe(true);
    });
    expect(calls()).toEqual([
      ['InstrumentEvents', { key: 'AAPL' }],
      ['InstrumentPrices', { key: 'AAPL', start: '2025-10-02' }],
    ]);
    expect(events.result.current.data).toEqual([]);
    expect(prices.result.current.data).toEqual([{ session: 'd' }]);
  });

  it('ask for feature values in chunks the API accepts, and merge them', async () => {
    GQL.mockClear();
    const names = Array.from({ length: NAMES_PER_REQUEST + 1 }, (_, i) => `feature.f${i}`);
    GQL.mockImplementation((_document, variables) => {
      const asked = (variables as { names: string[] }).names;
      return Promise.resolve({
        session: { date: '2026-10-02' },
        instrument: { instrumentId: 'EQ:A', features: asked.map(value) },
      });
    });
    const { result } = renderHook(() => useFeatureValues('AAPL', names), { wrapper });
    await waitFor(() => {
      expect(result.current.isPending).toBe(false);
    });
    // The first chunk resolves the session; the rest ask for exactly that date.
    expect(calls().map(([, v]) => v)).toEqual([
      expect.objectContaining({ names: names.slice(0, NAMES_PER_REQUEST), date: null }),
      expect.objectContaining({ names: names.slice(NAMES_PER_REQUEST), date: '2026-10-02' }),
    ]);
    expect(result.current.session).toBe('2026-10-02');
    expect(result.current.values.size).toBe(names.length);
    expect(result.current.isError).toBe(false);
  });

  it('read the history only once its start is known', async () => {
    GQL.mockClear();
    GQL.mockResolvedValue({
      instrument: { instrumentId: 'EQ:A', series: { names: ['x'], points: [] } },
    });
    const idle = renderHook(() => useFeatureHistory('AAPL', ['x'], null, null), { wrapper });
    expect(idle.result.current.series).toEqual([]);
    expect(GQL).not.toHaveBeenCalled();
    const { result } = renderHook(
      () => useFeatureHistory('AAPL', ['x'], '2026-07-04', '2026-10-02'),
      {
        wrapper,
      },
    );
    await waitFor(() => {
      expect(result.current.isPending).toBe(false);
    });
    expect(calls()).toEqual([
      ['InstrumentHistory', { key: 'AAPL', names: ['x'], start: '2026-07-04', date: '2026-10-02' }],
    ]);
    expect(result.current.series).toEqual([{ names: ['x'], points: [] }]);
  });

  it('read nothing without a ticker', () => {
    GQL.mockClear();
    const { result } = renderHook(() => useInstrumentEvents(null), { wrapper });
    expect(result.current.fetchStatus).toBe('idle');
    expect(GQL).not.toHaveBeenCalled();
  });
});
