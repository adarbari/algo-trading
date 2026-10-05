import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { gql } from '@/shared/api';

import { useCellDetail, useCompleteness, useFocusCell } from './queries';

vi.mock('@/shared/api', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  gql: vi.fn(),
}));

const GQL = vi.mocked(gql);

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const grid = {
  sessions: ['2026-10-02'],
  datasets: ['bars/1d'],
  lastClosed: '2026-10-02',
  cells: [
    {
      dataset: 'bars/1d',
      session: '2026-10-02',
      status: 'PARTIAL',
      present: 1,
      expected: 2,
      basis: '',
      runIds: [],
    },
  ],
};

describe('ingestion queries', () => {
  beforeEach(() => {
    GQL.mockReset();
  });

  it('reads the last ten sessions of the grid', async () => {
    GQL.mockResolvedValue({ completeness: grid });
    const { result } = renderHook(() => useCompleteness(), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    const [document, variables] = GQL.mock.calls[0] ?? [];
    expect(String(document)).toContain('query IngestionCompleteness');
    expect(variables).toEqual({ sessions: 10 });
    expect(result.current.data).toEqual(grid);
  });

  it('reads nothing stored as null', async () => {
    GQL.mockResolvedValue({ completeness: null });
    const { result } = renderHook(() => useCompleteness(), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data).toBeNull();
  });

  it('reads a cell only once one is chosen', async () => {
    GQL.mockResolvedValue({ ingestionCell: { job: 'daily_bars' } });
    const { result: none } = renderHook(() => useCellDetail(null), { wrapper });
    expect(none.current.fetchStatus).toBe('idle');
    const cell = { dataset: 'chains/option_quotes', session: '2026-10-02' };
    const { result } = renderHook(() => useCellDetail(cell), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    const [document, variables] = GQL.mock.calls[0] ?? [];
    expect(String(document)).toContain('query IngestionCell');
    expect(variables).toEqual({ dataset: 'chains/option_quotes', date: '2026-10-02' });
  });

  it('focuses the selected cell, else the default one', async () => {
    GQL.mockResolvedValue({ completeness: grid });
    const chosen = { dataset: 'x', session: 'y' };
    const { result: selected } = renderHook(() => useFocusCell(chosen), { wrapper });
    expect(selected.current).toBe(chosen);
    const { result } = renderHook(() => useFocusCell(null), { wrapper });
    await waitFor(() => {
      expect(result.current).toEqual({ dataset: 'bars/1d', session: '2026-10-02' });
    });
  });
});
