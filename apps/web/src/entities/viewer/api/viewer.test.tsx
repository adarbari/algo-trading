import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { ApiError, gql } from '@/shared/api';

import { ensureViewer, forgetUser, useViewer } from './viewer';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    gql: vi.fn(),
  };
});

const GQL = vi.mocked(gql);
const TRADER = { id: 'ann', name: 'Ann', role: 'trader', workspaces: ['trader'] };

function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { client, wrapper };
}

describe('the viewer', () => {
  it('reads who is calling in one request', async () => {
    GQL.mockResolvedValue({ viewer: TRADER });
    const { wrapper } = setup();
    const { result } = renderHook(() => useViewer(), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data).toEqual(TRADER);
    expect(String(GQL.mock.calls[0]?.[0])).toContain('query Viewer');
  });

  it('is null (signed out) when the API says 401', async () => {
    GQL.mockRejectedValue(new ApiError(401, 'Unauthorized'));
    const { client } = setup();
    await expect(ensureViewer(client)).resolves.toBeNull();
  });

  it('stays an error for a 403: a valid token the registry does not know', async () => {
    GQL.mockRejectedValue(new ApiError(403, 'Forbidden'));
    const { client } = setup();
    await expect(ensureViewer(client)).rejects.toMatchObject({ status: 403 });
  });

  it('forgetUser empties the cache, cancels reads and leaves the viewer null', async () => {
    GQL.mockResolvedValue({ viewer: TRADER });
    const { client, wrapper } = setup();
    const { result } = renderHook(() => useViewer(), { wrapper });
    await waitFor(() => {
      expect(result.current.data).toEqual(TRADER);
    });
    client.setQueryData(['gql', 'Secret'], { private: 1 });
    act(() => {
      forgetUser(client);
    });
    expect(client.getQueryData(['gql', 'Secret'])).toBeUndefined();
    await waitFor(() => {
      expect(result.current.data).toBeNull();
    });
  });
});
