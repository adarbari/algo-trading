import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { api } from '@/shared/api';

import { fetchTickerTable, TICKER_PAGE_SIZE, useComparePrices, useTickerTable } from './hooks';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, api: { GET: vi.fn() } };
});

const GET = vi.mocked(api.GET);

function page(n: number, total: number) {
  const items = Array.from(
    { length: Math.min(TICKER_PAGE_SIZE, total - (n - 1) * TICKER_PAGE_SIZE) },
    (_, i) => ({
      instrument_id: `EQ:${n}-${i}`,
      symbol: `T${n}-${i}`,
      company_name: `Ticker ${n}-${i}`,
      security_type: 'ETF',
      'rollup.iv30@v1.iv30': 0.2,
    }),
  );
  return {
    data: {
      session: '2026-10-02',
      snapshot_date: '2026-10-02',
      pre_snapshot: false,
      columns: ['rollup.iv30@v1.iv30'],
      sort: 'symbol',
      missing: [],
      page: { total, page: n, size: TICKER_PAGE_SIZE, items },
    },
    response: new Response(null, { status: 200 }),
  };
}

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  GET.mockReset();
});

describe('ticker table', () => {
  it('fetches the first page, then the rest in parallel, and joins them', async () => {
    const total = 2 * TICKER_PAGE_SIZE + 427;
    GET.mockImplementation(((_path: string, init: { params: { query: { page: number } } }) =>
      Promise.resolve(page(init.params.query.page, total))) as never);
    const table = await fetchTickerTable({
      columns: ['rollup.iv30@v1.iv30'],
      securityType: 'ETF',
      optionable: true,
    });
    expect(GET).toHaveBeenCalledTimes(3);
    expect(GET.mock.calls[0]?.[1]).toMatchObject({
      params: {
        query: {
          page: 1,
          size: TICKER_PAGE_SIZE,
          columns: 'rollup.iv30@v1.iv30',
          security_type: 'ETF',
          optionable: true,
          leveraged: null,
          sector: null,
        },
      },
    });
    expect(table.rows).toHaveLength(total);
    expect(table.total).toBe(total);
    expect(table.rows[0]).toEqual({
      symbol: 'T1-0',
      instrumentId: 'EQ:1-0',
      name: 'Ticker 1-0',
      securityType: 'ETF',
      values: { 'rollup.iv30@v1.iv30': 0.2 },
    });
    expect(table.session).toBe('2026-10-02');
  });

  it('serves the table through a query hook', async () => {
    GET.mockResolvedValue(page(1, 3));
    const { result } = renderHook(() => useTickerTable({ columns: [] }), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data?.rows.map((r) => r.symbol)).toEqual(['T1-0', 'T1-1', 'T1-2']);
    expect(GET.mock.calls[0]?.[1]).toMatchObject({ params: { query: { columns: null } } });
  });

  it('surfaces API errors', async () => {
    GET.mockResolvedValue({
      error: { detail: 'columns: unknown feature' },
      response: new Response(null, { status: 400 }),
    });
    const { result } = renderHook(() => useTickerTable({ columns: ['nope'] }), { wrapper });
    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(result.current.error?.message).toBe('API 400: columns: unknown feature');
  });
});

describe('compare prices', () => {
  it('asks for the window rebased to 100, and nothing without tickers', async () => {
    GET.mockResolvedValue({ data: { instruments: [] }, response: new Response() });
    const empty = renderHook(() => useComparePrices([], '2025-10-02'), { wrapper });
    expect(empty.result.current.fetchStatus).toBe('idle');
    const { result } = renderHook(() => useComparePrices(['AAPL', 'MSFT'], '2025-10-02'), {
      wrapper,
    });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(GET).toHaveBeenCalledWith('/explore/compare/prices', {
      params: { query: { ids: 'AAPL,MSFT', from: '2025-10-02', rebase: 100 } },
    });
  });
});
