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
  narrowColumns: ['name'],
  sort: '-score',
  decisions: ['QUALIFIED'],
  filters: 'decision:QUALIFIED;gone:1..2',
  names: ['Earnings'],
  ...patch,
});

/** The REST response of a save: the view with the snake_case key. */
const restView = (patch: Record<string, unknown> = {}) => {
  const { narrowColumns, ...rest } = view(patch);
  return { ...rest, narrow_columns: narrowColumns };
};

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
    PUT.mockResolvedValue(ok(restView({ sort: 'symbol' })));
    const { result } = renderHook(() => useTableView(SCOPE), { wrapper });
    await waitFor(() => {
      expect(result.current.ready).toBe(true);
    });
    expect(GQL.mock.calls[0]?.[1]).toEqual({ scope: SCOPE, name: null });
    expect(result.current).toMatchObject({
      name: null,
      names: ['Earnings'],
      columns: [CLOSE],
      narrowColumns: ['name'],
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
        body: {
          columns: [CLOSE],
          narrow_columns: ['name'],
          sort: 'symbol',
          decisions: ['QUALIFIED'],
          filters: 'decision:QUALIFIED;gone:1..2', // no binding: the saved f is kept
        },
      });
    });
  });

  it('saves the URL f with the view, restores the saved f on first load, and says what it drops', async () => {
    GQL.mockResolvedValue({ view: view() });
    PUT.mockResolvedValue(ok(restView()));
    const onChange = vi.fn();
    const { result, rerender } = renderHook(
      ({ f }: { f: string | undefined }) =>
        useTableView(SCOPE, { f, onChange, known: ['decision', 'dte'] }),
      { wrapper, initialProps: { f: undefined as string | undefined } },
    );
    await waitFor(() => {
      expect(onChange).toHaveBeenCalledWith('decision:QUALIFIED');
    });
    expect(result.current.droppedFilters).toEqual(['gone']);
    rerender({ f: 'dte:..14' });
    act(() => {
      result.current.change({ sort: 'symbol' });
    });
    await waitFor(() => {
      expect(PUT.mock.calls[0]?.[1]).toMatchObject({ body: { filters: 'dte:..14' } });
    });
  });

  it("keeps a shared link's f over the default view's, but a picked view replaces it", async () => {
    GQL.mockResolvedValue({ view: view() });
    const onChange = vi.fn();
    const { result } = renderHook(
      () => useTableView(SCOPE, { f: 'dte:..5s', onChange, known: ['decision', 'dte'] }),
      { wrapper },
    );
    await waitFor(() => {
      expect(result.current.ready).toBe(true);
    });
    expect(onChange).not.toHaveBeenCalled();
    GQL.mockResolvedValue({ view: view({ name: 'Earnings', filters: '' }) });
    act(() => {
      result.current.select('Earnings');
    });
    await waitFor(() => {
      expect(onChange).toHaveBeenCalledWith(undefined);
    });
  });

  it('a view stored before filters existed restores no f', async () => {
    const { filters: _omitted, ...legacy } = view();
    GQL.mockResolvedValue({ view: legacy });
    const onChange = vi.fn();
    const { result } = renderHook(
      () => useTableView(SCOPE, { f: undefined, onChange, known: ['decision'] }),
      { wrapper },
    );
    await waitFor(() => {
      expect(result.current.ready).toBe(true);
    });
    expect(onChange).toHaveBeenCalledWith(undefined);
    expect(result.current.droppedFilters).toEqual([]);
  });

  it('a view with no filters is seeded by the fallback: nothing saved, or only decisions saved', async () => {
    const fallback = vi.fn((decisions: readonly string[]) =>
      decisions.length > 0 ? `decision:${decisions.join(',')}` : 'decision:QUALIFIED',
    );
    GQL.mockResolvedValue({ view: view({ saved: false, filters: '', decisions: [] }) });
    const first = vi.fn();
    const one = renderHook(
      () => useTableView(SCOPE, { f: undefined, onChange: first, known: ['decision'], fallback }),
      { wrapper },
    );
    await waitFor(() => {
      expect(first).toHaveBeenCalledWith('decision:QUALIFIED');
    });
    one.unmount();
    GQL.mockResolvedValue({ view: view({ filters: '', decisions: ['WATCH', 'REJECT'] }) });
    const second = vi.fn();
    renderHook(
      () => useTableView(SCOPE, { f: undefined, onChange: second, known: ['decision'], fallback }),
      { wrapper },
    );
    await waitFor(() => {
      expect(second).toHaveBeenCalledWith('decision:WATCH,REJECT');
    });
  });

  it('a table with no view stored at all (the server answers null) is seeded by the fallback and ready', async () => {
    GQL.mockResolvedValue({ view: null });
    const onChange = vi.fn();
    const { result } = renderHook(
      () =>
        useTableView(SCOPE, {
          f: undefined,
          onChange,
          known: ['decision'],
          fallback: () => 'decision:QUALIFIED',
        }),
      { wrapper },
    );
    await waitFor(() => {
      expect(result.current.ready).toBe(true);
    });
    expect(onChange).toHaveBeenCalledWith('decision:QUALIFIED');
  });

  it('with a filter binding, is not ready until the view has been read and its f restored', async () => {
    GQL.mockResolvedValue({ view: view() });
    const { result, rerender } = renderHook(
      ({ known }: { known: string[] | undefined }) =>
        useTableView(SCOPE, { f: undefined, onChange: vi.fn(), ...(known && { known }) }),
      { wrapper, initialProps: { known: undefined as string[] | undefined } },
    );
    await waitFor(() => {
      expect(GQL).toHaveBeenCalled();
    });
    expect(result.current.ready).toBe(false);
    rerender({ known: ['decision', 'gone'] });
    await waitFor(() => {
      expect(result.current.ready).toBe(true);
    });
  });

  it('nothing saved: empty lists and no decisions (the table applies its defaults)', async () => {
    GQL.mockResolvedValue({
      view: view({ saved: false, columns: [], narrowColumns: [], sort: null, decisions: [] }),
    });
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

  it('saves the columns added on a narrow table into the view', async () => {
    GQL.mockResolvedValue({ view: view() });
    PUT.mockResolvedValue(ok(restView({ narrowColumns: ['name', 'change'] })));
    const { result } = renderHook(() => useTableView(SCOPE), { wrapper });
    await waitFor(() => {
      expect(result.current.ready).toBe(true);
    });
    act(() => {
      result.current.change({ narrowColumns: ['name', 'change'] });
    });
    expect(result.current.narrowColumns).toEqual(['name', 'change']);
    await waitFor(() => {
      expect(PUT.mock.calls[0]?.[1]).toMatchObject({
        body: { narrow_columns: ['name', 'change'] },
      });
    });
  });

  it('saves the current choice under a name, switches to it, and removes it', async () => {
    GQL.mockResolvedValue({ view: view() });
    PUT.mockResolvedValue(ok(restView({ name: 'Mine', names: ['Earnings', 'Mine'] })));
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
