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
  it('starts the regime, ideas, filter definitions and edge desk reads before the page renders', async () => {
    const queryClient = new QueryClient();
    const load = ideasRoute.options.loader as (a: unknown) => Promise<void>;
    await load({ context: { queryClient } });
    // three reads in flight, none awaited: the loader never waits for data
    expect(vi.mocked(gql)).toHaveBeenCalledTimes(4);
    expect(queryClient.isFetching()).toBe(4);
  });
});
