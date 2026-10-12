import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { gql } from '@/shared/api';

import { REQUESTS_FIXTURE } from '../model/fixtures';
import { useFeatureRequests } from './queries';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, gql: vi.fn() };
});

const GQL = vi.mocked(gql);

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  GQL.mockReset();
});

describe('useFeatureRequests', () => {
  it('asks FeatureRequests and returns the ranked list', async () => {
    GQL.mockResolvedValue({ featureRequests: REQUESTS_FIXTURE });
    const { result } = renderHook(() => useFeatureRequests(), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(String(GQL.mock.calls[0]?.[0])).toContain('query FeatureRequests');
    expect(result.current.data?.rows).toHaveLength(5);
  });
});
