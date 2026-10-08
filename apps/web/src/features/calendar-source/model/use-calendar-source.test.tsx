import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { gql, TestQueryProvider } from '@/shared/api';

import { useCalendarSource } from './use-calendar-source';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, gql: vi.fn() };
});

const GQL = vi.mocked(gql);

function wrapper({ children }: { children: ReactNode }) {
  return <TestQueryProvider>{children}</TestQueryProvider>;
}

describe('useCalendarSource', () => {
  beforeEach(() => {
    GQL.mockReset();
  });

  it('lists a screener id once when a user screener and a site preset share it', async () => {
    GQL.mockResolvedValue({
      configs: [{ configId: 'vrp_scanner' }, { configId: 'vrp_scanner' }, { configId: 'momentum' }],
    });
    const { result } = renderHook(() => useCalendarSource(), { wrapper });
    await waitFor(() => {
      expect(result.current.screeners).toHaveLength(2);
    });
    expect(result.current.screeners).toEqual(['vrp_scanner', 'momentum']);
  });
});
