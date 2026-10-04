import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { api } from '@/shared/api';

import { useFeatureCatalogue, useFeatureDistribution } from './hooks';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, api: { GET: vi.fn() } };
});

const GET = vi.mocked(api.GET);

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe('feature hooks', () => {
  it('reads the catalogue', async () => {
    GET.mockResolvedValue({
      data: [{ name: 'feature.market_cap' }],
      response: new Response(),
    });
    const { result } = renderHook(() => useFeatureCatalogue(), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(GET).toHaveBeenCalledWith('/features');
    expect(result.current.data).toEqual([{ name: 'feature.market_cap' }]);
  });

  it('reads a distribution by name, and nothing without one', async () => {
    GET.mockClear();
    GET.mockResolvedValue({
      data: { name: 'instrument.sector' },
      response: new Response(),
    });
    const idle = renderHook(() => useFeatureDistribution(null), { wrapper });
    expect(idle.result.current.fetchStatus).toBe('idle');
    const { result } = renderHook(() => useFeatureDistribution('instrument.sector'), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(GET).toHaveBeenCalledWith('/features/{name}/distribution', {
      params: { path: { name: 'instrument.sector' } },
    });
  });
});
