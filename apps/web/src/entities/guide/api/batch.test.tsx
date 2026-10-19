import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { gql } from '@/shared/api';

import { useGuideEpisode, useGuideIndicator, useGuideTerm } from './hooks';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, gql: vi.fn() };
});

const GQL = vi.mocked(gql);

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const INDICATORS = ['curve_10y3m', 'vix_level', 'credit_spread'];
const EPISODES = ['gfc_2007', 'covid_2020', 'hikes_2022'];

beforeEach(() => {
  GQL.mockReset();
  GQL.mockResolvedValue({
    guideEntries: {
      indicators: INDICATORS.map((key) => ({ key, plainName: key })),
      episodes: EPISODES.map((key) => ({ episode: { key, name: key } })),
      terms: [],
      startPages: [],
    },
  });
});

describe('the Guide batch', () => {
  it('reads every entry a page asks for in one request', async () => {
    // The Regime page mounts one help button per indicator and per fall: 8 + 12 requests before.
    const { result } = renderHook(
      () => ({
        indicators: INDICATORS.map((key) => useGuideIndicator(key)),
        episodes: EPISODES.map((slug) => useGuideEpisode(slug)),
        term: useGuideTerm('nope'),
      }),
      { wrapper },
    );
    await waitFor(() => {
      expect(result.current.term.isSuccess).toBe(true);
    });
    expect(GQL).toHaveBeenCalledOnce();
    const [document, variables] = GQL.mock.calls[0] ?? [];
    expect(String(document)).toContain('query GuideEntries');
    expect(variables).toEqual({
      refs: [
        ...INDICATORS.map((id) => ({ kind: 'INDICATOR', id })),
        ...EPISODES.map((id) => ({ kind: 'EPISODE', id })),
        { kind: 'TERM', id: 'nope' },
      ],
    });
  });

  it('gives each hook its own entry, and null for an entry the Guide lacks', async () => {
    const { result } = renderHook(
      () => ({
        indicator: useGuideIndicator('vix_level'),
        episode: useGuideEpisode('hikes_2022'),
        term: useGuideTerm('nope'),
      }),
      { wrapper },
    );
    await waitFor(() => {
      expect(result.current.term.isSuccess).toBe(true);
    });
    expect(result.current.indicator.data?.key).toBe('vix_level');
    expect(result.current.episode.data?.episode.key).toBe('hikes_2022');
    expect(result.current.term.data).toBeNull();
  });

  it('fails every waiting hook when the request fails', async () => {
    GQL.mockRejectedValue(new Error('down'));
    const { result } = renderHook(
      () => ({ a: useGuideIndicator('curve_10y3m'), b: useGuideEpisode('gfc_2007') }),
      { wrapper },
    );
    await waitFor(() => {
      expect(result.current.a.isError && result.current.b.isError).toBe(true);
    });
    expect(GQL).toHaveBeenCalledOnce();
  });
});
