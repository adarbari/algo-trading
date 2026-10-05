import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { api, gql } from '@/shared/api';

import { useTableView } from './table-view';
import { formatSort, parseSort, screenerScope } from './view';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, api: { PUT: vi.fn(), DELETE: vi.fn() }, gql: vi.fn() };
});

const PUT = vi.mocked(api.PUT);
const DELETE = vi.mocked(api.DELETE);
const GQL = vi.mocked(gql);
const ok = <T,>(data: T) => ({ data, response: new Response(null, { status: 200 }) });
const SCOPE = 'screener:vrp';
const CLOSE = 'rollup.price_stats@v2.close';

const view = (patch: Record<string, unknown> = {}) => ({
  scope: SCOPE,
  name: null,
  saved: true,
  columns: [CLOSE],
  sort: '-score',
  decisions: ['QUALIFIED'],
  names: ['Earnings'],
  ...patch,
});

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  PUT.mockReset();
  DELETE.mockReset();
  GQL.mockReset();
});

describe('useTableView', () => {
  it('starts from the saved view and saves every change into the view in use', async () => {
    GQL.mockResolvedValue({ view: view() });
    PUT.mockResolvedValue(ok(view({ sort: 'symbol' })));
    const { result } = renderHook(() => useTableView(SCOPE), { wrapper });
    await waitFor(() => {
      expect(result.current.ready).toBe(true);
    });
    expect(GQL.mock.calls[0]?.[1]).toEqual({ scope: SCOPE, name: null });
    expect(result.current).toMatchObject({
      name: null,
      names: ['Earnings'],
      columns: [CLOSE],
      sort: '-score',
      decisions: ['QUALIFIED'],
    });
    act(() => {
      result.current.change({ sort: 'symbol' });
    });
    expect(result.current.sort).toBe('symbol');
    await waitFor(() => {
      expect(PUT).toHaveBeenCalledWith('/preferences/views/{scope}/view', {
        params: { path: { scope: SCOPE }, query: { name: null } },
        body: { columns: [CLOSE], sort: 'symbol', decisions: ['QUALIFIED'] },
      });
    });
  });

  it('nothing saved: empty lists and no decisions (the table applies its defaults)', async () => {
    GQL.mockResolvedValue({ view: view({ saved: false, columns: [], sort: null, decisions: [] }) });
    const { result } = renderHook(() => useTableView(SCOPE), { wrapper });
    await waitFor(() => {
      expect(result.current.ready).toBe(true);
    });
    expect([result.current.columns, result.current.sort, result.current.decisions]).toEqual([
      [],
      null,
      null,
    ]);
  });

  it('saves the current choice under a name, switches to it, and removes it', async () => {
    GQL.mockResolvedValue({ view: view() });
    PUT.mockResolvedValue(ok(view({ name: 'Mine', names: ['Earnings', 'Mine'] })));
    DELETE.mockResolvedValue(ok({ names: ['Earnings'] }));
    const { result } = renderHook(() => useTableView(SCOPE), { wrapper });
    await waitFor(() => {
      expect(result.current.ready).toBe(true);
    });
    const done = vi.fn();
    act(() => {
      result.current.saveAs('Mine', done);
    });
    await waitFor(() => {
      expect(result.current.name).toBe('Mine');
    });
    expect(done).toHaveBeenCalled();
    expect(PUT.mock.calls[0]?.[1]).toMatchObject({ params: { query: { name: 'Mine' } } });
    act(() => {
      result.current.remove();
    });
    await waitFor(() => {
      expect(result.current.name).toBeNull();
    });
    expect(DELETE).toHaveBeenCalledWith('/preferences/views/{scope}/view', {
      params: { path: { scope: SCOPE }, query: { name: 'Mine' } },
    });
  });

  it('removing the default view does nothing', () => {
    GQL.mockResolvedValue({ view: view() });
    const { result } = renderHook(() => useTableView(SCOPE), { wrapper });
    act(() => {
      result.current.remove();
    });
    expect(DELETE).not.toHaveBeenCalled();
  });
});

describe('view helpers', () => {
  it('scope a screener and read and write a sort, the default saved as none', () => {
    expect(screenerScope('vrp')).toBe('screener:vrp');
    const rank = { columnId: 'rank', direction: 'asc' } as const;
    expect(parseSort('-criterion:iv30', rank)).toEqual({
      columnId: 'criterion:iv30',
      direction: 'desc',
    });
    expect(parseSort('symbol', rank)).toEqual({ columnId: 'symbol', direction: 'asc' });
    expect(parseSort(null, rank)).toBe(rank);
    expect(formatSort({ columnId: 'score', direction: 'desc' })).toBe('-score');
    expect(formatSort(rank, rank)).toBeNull();
    expect(formatSort(null)).toBeNull();
    expect(formatSort({ columnId: 'symbol', direction: 'asc' }, rank)).toBe('symbol');
  });
});
