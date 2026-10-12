import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { gql } from '@/shared/api';

import { FORMULAS_FIXTURE } from '../model/fixtures';
import { useAcceptedFormulas } from './queries';

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

describe('useAcceptedFormulas', () => {
  it('asks AcceptedFormulas and returns the grouped list', async () => {
    GQL.mockResolvedValue({ acceptedFormulas: FORMULAS_FIXTURE });
    const { result } = renderHook(() => useAcceptedFormulas(), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(String(GQL.mock.calls[0]?.[0])).toContain('query AcceptedFormulas');
    expect(result.current.data?.rows).toHaveLength(3);
  });
});
