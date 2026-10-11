import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { saveTextFile } from '@algotrade/ui';
import { api } from '@/shared/api';

import { useTradesCsv } from './use-trades-csv';

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

describe('useTradesCsv', () => {
  it("fetches the period's CSV with the user's token and saves it under a name that says what it is", async () => {
    GET.mockResolvedValue({ data: 'a,b\n', response: new Response() });
    const { result } = renderHook(() => useTradesCsv('drift'), { wrapper });
    result.current.mutate('IN_SAMPLE');
    await waitFor(() => {
      expect(saveTextFile).toHaveBeenCalledWith('drift-trades-in_sample.csv', 'a,b\n');
    });
    expect(GET.mock.calls[0]?.[0]).toBe('/files/edges/{edge_id}/trades.csv');
    expect(GET.mock.calls[0]?.[1]).toMatchObject({
      params: { path: { edge_id: 'drift' }, query: { period: 'in_sample' } },
    });
  });

  it('fails with the server detail when there is no ledger to read', async () => {
    GET.mockResolvedValue({
      error: { detail: 'no ledger to read: NOT_STORED' },
      response: new Response(null, { status: 404 }),
    });
    const { result } = renderHook(() => useTradesCsv('drift'), { wrapper });
    result.current.mutate('ALL');
    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(saveTextFile).not.toHaveBeenCalled();
  });
});
