import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { gql, TestQueryProvider } from '@/shared/api';

import { useMyFeatureRequests } from './feature-requests';

vi.mock('@/shared/api', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  gql: vi.fn(),
}));

const GQL = vi.mocked(gql);

function wrapper({ children }: { children: ReactNode }) {
  return <TestQueryProvider>{children}</TestQueryProvider>;
}

beforeEach(() => {
  GQL.mockReset();
});

describe('useMyFeatureRequests', () => {
  it("reads the viewer's own history over GraphQL, with no argument that could name another user", async () => {
    const own = { ref: 'moat_score', timesAsked: 2 };
    GQL.mockResolvedValue({ myFeatureRequests: [own] });
    const { result } = renderHook(() => useMyFeatureRequests(true), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    const [document, variables] = GQL.mock.calls[0] ?? [];
    expect(String(document)).toContain('myFeatureRequests');
    expect(variables).toEqual({});
    expect(result.current.data).toEqual([own]);
  });

  it('reads nothing until a draft names something missing', () => {
    renderHook(() => useMyFeatureRequests(false), { wrapper });
    expect(GQL).not.toHaveBeenCalled();
  });
});
