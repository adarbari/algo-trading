import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { gql } from '@/shared/api';

import { eventScope } from '../model/fixtures';
import { refreshEventScope, useEventScope } from './queries';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, gql: vi.fn() };
});

const GQL = vi.mocked(gql);

function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { client, wrapper };
}

beforeEach(() => {
  GQL.mockReset();
});

describe('useEventScope', () => {
  it('asks EventScope and returns the list', async () => {
    GQL.mockResolvedValue({ eventScope: eventScope() });
    const { wrapper } = setup();
    const { result } = renderHook(() => useEventScope(), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(String(GQL.mock.calls[0]?.[0])).toContain('query EventScope');
    expect(result.current.data?.names.map((n) => n.symbol)).toEqual(['AAPL', 'MSFT']);
  });
});

describe('refreshEventScope', () => {
  it('invalidates the list and the Calendar that reads the same scope', async () => {
    const { client } = setup();
    const spy = vi.spyOn(client, 'invalidateQueries');
    await refreshEventScope(client);
    const keys = spy.mock.calls.map((c) => c[0]?.queryKey);
    expect(keys).toEqual([
      ['gql', 'EventScope'],
      ['gql', 'EventCalendar'],
    ]);
  });
});
