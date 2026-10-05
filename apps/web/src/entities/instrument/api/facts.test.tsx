import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { feature, gql } from '@/shared/api';

import { useInstrumentFacts } from './facts';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, gql: vi.fn() };
});

const GQL = vi.mocked(gql);

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe('useInstrumentFacts', () => {
  it('asks the InstrumentFacts operation for the names, in one request', async () => {
    GQL.mockResolvedValue({ session: null, instrument: null });
    const names = [feature('rollup.earnings@v1.next_earnings_date'), feature('feature.market_cap')];
    const { result } = renderHook(() => useInstrumentFacts('MRVL', names), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(GQL).toHaveBeenCalledTimes(1);
    const [document, variables] = GQL.mock.calls[0] ?? [];
    expect(String(document)).toContain('query InstrumentFacts');
    expect(variables).toEqual({ key: 'MRVL', names });
  });

  it('reads nothing without a ticker', () => {
    GQL.mockClear();
    const { result } = renderHook(() => useInstrumentFacts(null, []), { wrapper });
    expect(result.current.fetchStatus).toBe('idle');
    expect(GQL).not.toHaveBeenCalled();
  });
});
