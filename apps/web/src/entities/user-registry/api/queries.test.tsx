import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { gql } from '@/shared/api';

import { PEOPLE_FIXTURE } from '../model/fixtures';
import { useUserRegistry } from './queries';

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

describe('useUserRegistry', () => {
  it('asks UserRegistry, selecting no email, and returns the people', async () => {
    GQL.mockResolvedValue({ userRegistry: { people: PEOPLE_FIXTURE } });
    const { result } = renderHook(() => useUserRegistry(), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    const query = String(GQL.mock.calls[0]?.[0]);
    expect(query).toContain('query UserRegistry');
    expect(query).not.toMatch(/email|subject/);
    expect(result.current.data?.people).toHaveLength(3);
  });
});
