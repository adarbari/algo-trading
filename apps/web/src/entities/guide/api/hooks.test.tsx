import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { gql } from '@/shared/api';

import { useGuideField, useGuideIndex, useGuideScreener, useGuideSituation } from './hooks';
import { useGuideEdge, useGuideEdgeIndex, useGuideMechanism } from './edges';
import { useGuideScreenerCategory, useGuideScreenerIndex } from './screeners';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, gql: vi.fn() };
});

const GQL = vi.mocked(gql);

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe('guide hooks', () => {
  it('reads the index over GraphQL', async () => {
    GQL.mockResolvedValue({ guideIndex: { sections: [], themeGroups: [], intents: [] } });
    const { result } = renderHook(() => useGuideIndex(), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(String(GQL.mock.calls[0]?.[0])).toContain('query GuideIndex');
    expect(result.current.data).toEqual({ sections: [], themeGroups: [], intents: [] });
  });

  it('reads the Edges index, and nothing while it is disabled', async () => {
    GQL.mockClear();
    GQL.mockResolvedValue({ guideEdgeIndex: { mechanisms: [], setAsideTitle: 'Set aside' } });
    const idle = renderHook(() => useGuideEdgeIndex({ enabled: false }), { wrapper });
    expect(idle.result.current.fetchStatus).toBe('idle');
    const { result } = renderHook(() => useGuideEdgeIndex(), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(String(GQL.mock.calls[0]?.[0])).toContain('query GuideEdgeIndex');
    expect(result.current.data?.setAsideTitle).toBe('Set aside');
  });

  it('reads a mechanism and a site edge by id, each in its own query', async () => {
    GQL.mockClear();
    GQL.mockResolvedValue({ guideMechanism: { id: 'm' }, guideEdge: { summary: { id: 'e' } } });
    const { result } = renderHook(
      () => ({ mechanism: useGuideMechanism('m'), edge: useGuideEdge('e') }),
      { wrapper },
    );
    await waitFor(() => {
      expect(result.current.mechanism.isSuccess && result.current.edge.isSuccess).toBe(true);
    });
    const asked = GQL.mock.calls.map(([document, variables]) => [String(document), variables]);
    expect(
      asked.some(
        ([d, v]) =>
          String(d).includes('query GuideMechanism') && JSON.stringify(v) === '{"id":"m"}',
      ),
    ).toBe(true);
    expect(
      asked.some(
        ([d, v]) => String(d).includes('query GuideEdge(') && JSON.stringify(v) === '{"id":"e"}',
      ),
    ).toBe(true);
    expect(result.current.mechanism.data?.id).toBe('m');
  });

  it('reads the Screeners lead page and a family’s page by id, each in its own query', async () => {
    GQL.mockClear();
    GQL.mockResolvedValue({
      guideScreenerIndex: { count: 3, categories: [] },
      guideScreenerCategory: { id: 'trend', screeners: [] },
    });
    const { result } = renderHook(
      () => ({ index: useGuideScreenerIndex(), category: useGuideScreenerCategory('trend') }),
      { wrapper },
    );
    await waitFor(() => {
      expect(result.current.index.isSuccess && result.current.category.isSuccess).toBe(true);
    });
    const asked = GQL.mock.calls.map(([document, variables]) => [String(document), variables]);
    expect(asked.some(([d]) => String(d).includes('query GuideScreenerIndex'))).toBe(true);
    expect(
      asked.some(
        ([d, v]) =>
          String(d).includes('query GuideScreenerCategory') &&
          JSON.stringify(v) === '{"id":"trend"}',
      ),
    ).toBe(true);
    expect(result.current.index.data?.count).toBe(3);
    expect(result.current.category.data?.id).toBe('trend');
  });

  it('reads a field’s derived parts by name, and nothing without one', async () => {
    GQL.mockClear();
    GQL.mockResolvedValue({
      guideField: { related: ['feature.y'], screeners: [], situations: [] },
    });
    const idle = renderHook(() => useGuideField(null), { wrapper });
    expect(idle.result.current.fetchStatus).toBe('idle');
    const { result } = renderHook(() => useGuideField('feature.x'), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data?.related).toEqual(['feature.y']);
    const [document, variables] = GQL.mock.calls[0] ?? [];
    expect(String(document)).toContain('query GuideField');
    expect(variables).toEqual({ name: 'feature.x' });
  });

  it('reads a screener by its preset id', async () => {
    GQL.mockClear();
    GQL.mockResolvedValue({ guideScreener: { id: 'breakout', criteria: [] } });
    const { result } = renderHook(() => useGuideScreener('breakout'), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data?.id).toBe('breakout');
    const [document, variables] = GQL.mock.calls[0] ?? [];
    expect(String(document)).toContain('query GuideScreener');
    expect(variables).toEqual({ id: 'breakout' });
  });

  it('reads a situation by its slug', async () => {
    GQL.mockClear();
    GQL.mockResolvedValue({ guideSituation: null });
    const { result } = renderHook(() => useGuideSituation('earnings-gap'), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data).toBeNull();
    const [document, variables] = GQL.mock.calls[0] ?? [];
    expect(String(document)).toContain('query GuideSituation');
    expect(variables).toEqual({ slug: 'earnings-gap' });
  });
});
