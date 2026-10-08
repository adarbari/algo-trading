import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { gql } from '@/shared/api';

import {
  refreshCatalogue,
  useFeatureCatalogue,
  useFeatureCatalogueDetail,
  useFeatureDistribution,
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

describe('feature hooks', () => {
  it('reads the catalogue over GraphQL', async () => {
    GQL.mockResolvedValue({ catalogue: [{ name: 'feature.market_cap' }] });
    const { result } = renderHook(() => useFeatureCatalogue(), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(String(GQL.mock.calls[0]?.[0])).toContain('query FeatureCatalogue');
    expect(result.current.data).toEqual([{ name: 'feature.market_cap' }]);
  });

  it('keeps the guide entries out of the light catalogue and reads them on the detail read', async () => {
    GQL.mockClear();
    GQL.mockResolvedValue({ catalogue: [] });
    const light = renderHook(() => useFeatureCatalogue(), { wrapper });
    const detail = renderHook(() => useFeatureCatalogueDetail(), { wrapper });
    await waitFor(() => {
      expect(light.result.current.isSuccess && detail.result.current.isSuccess).toBe(true);
    });
    const documents = GQL.mock.calls.map(([document]) => String(document));
    const lightDoc = documents.find((d) => d.includes('query FeatureCatalogue {')) ?? '';
    const detailDoc = documents.find((d) => d.includes('query FeatureCatalogueDetail')) ?? '';
    expect(lightDoc).not.toContain('caveats');
    expect(lightDoc).not.toContain('uses');
    expect(detailDoc).toContain('caveats');
    expect(detailDoc).toContain('uses');
  });

  it('reads a distribution by name, and nothing without one', async () => {
    GQL.mockClear();
    GQL.mockResolvedValue({ distribution: { name: 'instrument.sector' } });
    const idle = renderHook(() => useFeatureDistribution(null), { wrapper });
    expect(idle.result.current.fetchStatus).toBe('idle');
    const { result } = renderHook(() => useFeatureDistribution('instrument.sector'), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data).toEqual({ name: 'instrument.sector' });
    const [document, variables] = GQL.mock.calls[0] ?? [];
    expect(String(document)).toContain('query FeatureDistribution');
    expect(variables).toEqual({ name: 'instrument.sector' });
  });

  it('reads the catalogue again after a user feature is saved', async () => {
    const client = new QueryClient();
    const invalidate = vi.spyOn(client, 'invalidateQueries');
    await refreshCatalogue(client);
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['gql', 'FeatureCatalogue', {}] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['gql', 'FeatureCatalogueDetail', {}] });
  });
});
