import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { gql } from '@/shared/api';

import { PICKS_LIMIT, useScreenerPicks } from './picks';

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

describe('useScreenerPicks', () => {
  it('asks for the ids of the picks only: no criteria, columns or reasons per row', async () => {
    GQL.mockResolvedValue({ screener: { latestRun: { results: { results: [] } } } });
    const { result } = renderHook(() => useScreenerPicks('momentum_12_1'), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    const document = String(GQL.mock.calls[0]?.[0]);
    expect(document).toContain('instrumentId');
    for (const heavy of ['criteria', 'reasons', 'columns', 'instrument {']) {
      expect(document).not.toContain(heavy);
    }
    expect(GQL.mock.calls[0]?.[1]).toMatchObject({ id: 'momentum_12_1', size: PICKS_LIMIT });
  });

  it('asks for nothing while disabled', () => {
    renderHook(() => useScreenerPicks('scope', false), { wrapper });
    expect(GQL).not.toHaveBeenCalled();
  });
});
