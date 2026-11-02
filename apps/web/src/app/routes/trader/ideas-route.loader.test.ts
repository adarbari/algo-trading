/** The Ideas route's loader starts the page's reads with its chunks, not when widgets mount. */
import { QueryClient } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';

import { gql } from '@/shared/api';

import { ideasRoute } from './ideas-route';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, gql: vi.fn(() => new Promise(() => undefined)) };
});

describe('ideas route loader', () => {
  it('starts the regime, setup ideas and filter definitions reads before the page renders', async () => {
    const queryClient = new QueryClient();
    const load = ideasRoute.options.loader as (a: unknown) => Promise<void>;
    await load({ context: { queryClient }, deps: { tab: undefined } });
    // these reads in flight, none awaited: the loader never waits for data
    expect(vi.mocked(gql)).toHaveBeenCalledTimes(3);
    expect(queryClient.isFetching()).toBe(3);
  });
});
