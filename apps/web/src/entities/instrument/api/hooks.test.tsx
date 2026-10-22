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

  /** An answer for the aliased slots `n0..` of a values request, as `f0..`. */
  const answerValues = (variables: unknown) => {
    const v = variables as Record<string, unknown>;
    return Promise.resolve({
      session: { date: '2026-10-02' },
      instrument: {
        instrumentId: 'EQ:A',
        ...Object.fromEntries(
          Array.from({ length: 10 }, (_, i) => [
            `f${String(i)}`,
            ((v[`n${String(i)}`] as string[] | undefined) ?? []).map(value),
          ]),
        ),
      },
    });
  };

  it('ask for all feature values in ONE request (aliased fields, chunks of the cap)', async () => {
    GQL.mockClear();
    const names = Array.from({ length: 5 * NAMES_PER_REQUEST + 1 }, (_, i) => `feature.f${i}`);
    GQL.mockImplementation((_document, variables) => answerValues(variables));
    const { result } = renderHook(() => useFeatureValues('AAPL', names), { wrapper });
    await waitFor(() => {
      expect(result.current.isPending).toBe(false);
    });
    expect(GQL).toHaveBeenCalledOnce();
    expect(calls()[0]?.[1]).toEqual(
      expect.objectContaining({
        key: 'AAPL',
        date: null,
        n0: names.slice(0, NAMES_PER_REQUEST),
        n5: names.slice(5 * NAMES_PER_REQUEST),
        n6: [],
      }),
    );
    expect(result.current.session).toBe('2026-10-02');
    expect(result.current.values.size).toBe(names.length);
    expect(result.current.isError).toBe(false);
  });

  it('ask for the names past the slots in a second request for the same date', async () => {
    GQL.mockClear();
    const names = Array.from({ length: 10 * NAMES_PER_REQUEST + 1 }, (_, i) => `feature.f${i}`);
    GQL.mockImplementation((_document, variables) => answerValues(variables));
    const { result } = renderHook(() => useFeatureValues('AAPL', names), { wrapper });
    await waitFor(() => {
      expect(result.current.isPending).toBe(false);
    });
    expect(calls().map(([, v]) => (v as { date: string | null }).date)).toEqual([
      null,
      '2026-10-02',
    ]);
    expect(result.current.values.size).toBe(names.length);
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

  it('read the first history chunk alone, the rest once it settled (failed too)', async () => {
    // All chunks at once kept the API busy for seconds before the first came back (Features).
    GQL.mockClear();
    const names = Array.from({ length: 2 * NAMES_PER_REQUEST + 1 }, (_, i) => `feature.f${i}`);
    let fail: () => void = () => undefined;
    GQL.mockImplementation((_document, variables) => {
      const asked = (variables as { names: string[] }).names;
      if (asked[0] === names[0]) {
        return new Promise((_resolve, reject) => {
          fail = () => {
            reject(new Error('down'));
          };
        });
      }
      return Promise.resolve({
        instrument: { instrumentId: 'EQ:A', series: { names: asked, points: [] } },
      });
    });
    const { result } = renderHook(
      () => useFeatureHistory('AAPL', names, '2026-07-04', '2026-10-02'),
      { wrapper },
    );
    await waitFor(() => {
      expect(GQL).toHaveBeenCalledOnce();
    });
    fail();
    await waitFor(() => {
      expect(result.current.isPending).toBe(false);
    });
    expect(GQL).toHaveBeenCalledTimes(3);
    expect(result.current.series).toHaveLength(2);
  });

  it('read only the history chunks that hold a shown name, each when first shown', async () => {
    GQL.mockClear();
    const names = Array.from({ length: 2 * NAMES_PER_REQUEST + 1 }, (_, i) => `feature.f${i}`);
    GQL.mockImplementation((_document, variables) =>
      Promise.resolve({
        instrument: {
          instrumentId: 'EQ:A',
          series: { names: (variables as { names: string[] }).names, points: [] },
        },
      }),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result, rerender } = renderHook(
      ({ shown }: { shown: ReadonlySet<string> }) =>
        useFeatureHistory('AAPL', names, '2026-07-04', '2026-10-02', shown),
      {
        wrapper: ({ children }: { children: ReactNode }) => (
          <QueryClientProvider client={client}>{children}</QueryClientProvider>
        ),
        initialProps: { shown: new Set(['feature.f1']) },
      },
    );
    await waitFor(() => {
      expect(result.current.isPending).toBe(false);
    });
    expect(GQL).toHaveBeenCalledOnce();
    rerender({ shown: new Set([names[2 * NAMES_PER_REQUEST] ?? '']) });
    await waitFor(() => {
      expect(GQL).toHaveBeenCalledTimes(2);
    });
    // the first chunk stays read when it scrolls away
    rerender({ shown: new Set() });
    expect(GQL).toHaveBeenCalledTimes(2);
    expect(result.current.series).toHaveLength(2);
  });

  it('read nothing without a ticker', () => {
    GQL.mockClear();
    const { result } = renderHook(() => useInstrumentEvents(null), { wrapper });
    expect(result.current.fetchStatus).toBe('idle');
    expect(GQL).not.toHaveBeenCalled();
  });
});
