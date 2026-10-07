import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { gql } from '@/shared/api';

import { STUDY_FIXTURE } from '../model/fixtures';

import { useEventCalendar } from './calendar';
import { useInstrumentEventStudy } from './study';

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

describe('useInstrumentEventStudy', () => {
  it('asks the InstrumentEventStudy operation for the ticker and serves its study', async () => {
    GQL.mockResolvedValue({
      session: { date: '2026-10-07' },
      instrument: { eventStudy: STUDY_FIXTURE },
    });
    const { result } = renderHook(() => useInstrumentEventStudy('AAPL'), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(String(GQL.mock.calls[0]?.[0])).toContain('query InstrumentEventStudy');
    expect(GQL.mock.calls[0]?.[1]).toEqual({ key: 'AAPL' });
    expect(result.current.data?.ahead).toHaveLength(3);
  });

  it('serves null for a ticker the snapshot lacks and asks nothing without one', async () => {
    GQL.mockResolvedValue({ session: null, instrument: null });
    const { result } = renderHook(() => useInstrumentEventStudy('ZZZZ'), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data).toBeNull();
    GQL.mockClear();
    renderHook(() => useInstrumentEventStudy(null), { wrapper });
    expect(GQL).not.toHaveBeenCalled();
  });
});

describe('useEventCalendar', () => {
  it('asks the EventCalendar operation for the scope list', async () => {
    GQL.mockResolvedValue({ eventCalendar: { days: [] } });
    const { result } = renderHook(() => useEventCalendar([], true), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(String(GQL.mock.calls[0]?.[0])).toContain('query EventCalendar');
    expect(GQL.mock.calls[0]?.[1]).toEqual({ instrumentIds: [], scope: true });
  });

  it('waits while disabled', () => {
    renderHook(() => useEventCalendar(['EQ:A'], false, false), { wrapper });
    expect(GQL).not.toHaveBeenCalled();
  });
});
