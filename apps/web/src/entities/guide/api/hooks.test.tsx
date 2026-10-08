import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { gql } from '@/shared/api';

import { useGuideField, useGuideIndex, useGuidePlaybook, useGuideSituation } from './hooks';

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

  it('reads a field’s derived parts by name, and nothing without one', async () => {
    GQL.mockClear();
    GQL.mockResolvedValue({
      guideField: { related: ['feature.y'], playbooks: [], situations: [] },
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

  it('reads a playbook by its preset id', async () => {
    GQL.mockClear();
    GQL.mockResolvedValue({ guidePlaybook: { id: 'breakout', criteria: [] } });
    const { result } = renderHook(() => useGuidePlaybook('breakout'), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data?.id).toBe('breakout');
    const [document, variables] = GQL.mock.calls[0] ?? [];
    expect(String(document)).toContain('query GuidePlaybook');
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
