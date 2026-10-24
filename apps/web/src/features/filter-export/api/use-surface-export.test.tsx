import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { saveTextFile } from '@algotrade/ui';
import { api } from '@/shared/api';

import { useSurfaceExport } from './use-surface-export';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, api: { GET: vi.fn() } };
});
vi.mock('@algotrade/ui', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  saveTextFile: vi.fn(),
}));

const GET = vi.mocked(api.GET);

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  GET.mockReset();
  vi.mocked(saveTextFile).mockReset();
});

describe('useSurfaceExport', () => {
  it("fetches the surface's CSV under the filters with the user's token and saves it", async () => {
    GET.mockResolvedValue({ data: 'a,b\n', response: new Response() });
    const { result } = renderHook(() => useSurfaceExport('ideas'), { wrapper });
    result.current.mutate({ f: 'decision:QUALIFIED', session: '2026-10-01' });
    await waitFor(() => {
      expect(saveTextFile).toHaveBeenCalledWith('ideas-2026-10-01.csv', 'a,b\n');
    });
    expect(GET.mock.calls[0]?.[0]).toBe('/files/{surface}.csv');
    expect(GET.mock.calls[0]?.[1]).toMatchObject({
      params: {
        path: { surface: 'ideas' },
        query: { f: 'decision:QUALIFIED', date: '2026-10-01' },
      },
    });
  });

  it('sends the screener and the added columns of a surface that has them', async () => {
    GET.mockResolvedValue({ data: 'a\n', response: new Response() });
    const { result } = renderHook(() => useSurfaceExport('screener_results'), { wrapper });
    result.current.mutate({
      f: 'decision:QUALIFIED',
      session: '2026-10-01',
      screener: 'vrp',
      columns: ['feature.market_cap'],
    });
    await waitFor(() => {
      expect(saveTextFile).toHaveBeenCalled();
    });
    expect(GET.mock.calls[0]?.[1]).toMatchObject({
      params: {
        path: { surface: 'screener_results' },
        query: {
          f: 'decision:QUALIFIED',
          date: '2026-10-01',
          screener: 'vrp',
          columns: ['feature.market_cap'],
        },
      },
    });
  });

  it('sends no f for no filters and fails with the server detail', async () => {
    GET.mockResolvedValue({
      error: { detail: 'ideas: filter is not offered' },
      response: new Response(null, { status: 403 }),
    });
    const { result } = renderHook(() => useSurfaceExport('ideas'), { wrapper });
    result.current.mutate({ f: '' });
    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(GET.mock.calls[0]?.[1]).toMatchObject({ params: { query: {} } });
    expect(saveTextFile).not.toHaveBeenCalled();
  });
});
