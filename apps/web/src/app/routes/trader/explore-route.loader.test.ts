/** The Explore route's loader preloads the opened tab's chunk and starts its reads with it. */
import { QueryClient } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';

import { gql } from '@/shared/api';

import { exploreRoute } from './explore-route';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, gql: vi.fn(() => new Promise(() => undefined)) };
});

async function load(search: Record<string, string>) {
  const queryClient = new QueryClient();
  vi.mocked(gql).mockClear();
  const run = exploreRoute.options.loader as (a: unknown) => Promise<void>;
  const deps = (exploreRoute.options.loaderDeps as (a: unknown) => unknown)({ search });
  await run({ context: { queryClient }, deps });
  return queryClient;
}

describe('explore route loader', () => {
  it('starts the screener hits read of the focused ticker for tab=hits', async () => {
    const queryClient = await load({ sel: 'NVDA', focus: 'NVDA', tab: 'hits' });
    expect(vi.mocked(gql)).toHaveBeenCalledTimes(1);
    expect(queryClient.isFetching()).toBe(1);
    expect(JSON.stringify(vi.mocked(gql).mock.calls[0])).toContain('NVDA');
  });

  it('starts the catalogue read for tab=features', async () => {
    await load({ sel: 'TXNM', focus: 'TXNM', tab: 'features' });
    expect(vi.mocked(gql)).toHaveBeenCalledTimes(1);
  });

  it('starts no read on the overview (its widgets are in the page)', async () => {
    const queryClient = await load({ sel: 'NVDA', focus: 'NVDA' });
    expect(vi.mocked(gql)).not.toHaveBeenCalled();
    expect(queryClient.isFetching()).toBe(0);
  });
});
