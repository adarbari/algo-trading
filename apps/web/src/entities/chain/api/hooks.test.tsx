import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { gql } from '@/shared/api';

import { CHAIN_FEATURES } from '../model/chain';

import { useOptionChain, useOptionQuotes } from './hooks';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, gql: vi.fn() };
});

const GQL = vi.mocked(gql);

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe('chain hooks', () => {
  it('read the chain with its facts, then one expiry of quotes', async () => {
    GQL.mockResolvedValue({ instrument: { instrumentId: 'EQ:AAPL', chain: { quotes: [] } } });
    const chain = renderHook(() => useOptionChain('AAPL'), { wrapper });
    const quotes = renderHook(() => useOptionQuotes('AAPL', '2026-11-20', '2026-10-02'), {
      wrapper,
    });
    await waitFor(() => {
      expect(chain.result.current.isSuccess && quotes.result.current.isSuccess).toBe(true);
    });
    const [[chainDoc, chainVars], [quotesDoc, quotesVars]] = GQL.mock.calls as unknown as [
      [unknown, unknown],
      [unknown, unknown],
    ];
    expect(String(chainDoc)).toContain('query OptionChain');
    expect(chainVars).toEqual({ key: 'AAPL', names: [...CHAIN_FEATURES] });
    expect(String(quotesDoc)).toContain('query OptionQuotes');
    expect(quotesVars).toEqual({ key: 'AAPL', expiry: '2026-11-20', date: '2026-10-02' });
    expect(quotes.result.current.data).toEqual([]);
  });

  it('read nothing without a ticker or an expiry', () => {
    GQL.mockClear();
    const chain = renderHook(() => useOptionChain(null), { wrapper });
    const quotes = renderHook(() => useOptionQuotes('AAPL', null, '2026-10-02'), { wrapper });
    expect(chain.result.current.fetchStatus).toBe('idle');
    expect(quotes.result.current.fetchStatus).toBe('idle');
    expect(GQL).not.toHaveBeenCalled();
  });
});
