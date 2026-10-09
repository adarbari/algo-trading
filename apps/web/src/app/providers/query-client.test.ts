import { describe, expect, it, vi } from 'vitest';

import { ApiError, GraphQLRequestError, queryKeys } from '@/shared/api';

import { createQueryClient, retryDelay, shouldRetry } from './query-client';

/** The listeners `onUnauthorized` registered: the test plays a sign-out arriving. */
const signOuts = vi.hoisted(() => new Set<() => void>());

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    onUnauthorized: (listener: () => void) => {
      signOuts.add(listener);
      return () => signOuts.delete(listener);
    },
  };
});

describe('shouldRetry', () => {
  it('never retries a 4xx answer: it will not change, so the query settles at once', () => {
    expect(shouldRetry(0, new ApiError(404, 'nothing stored'))).toBe(false);
    expect(shouldRetry(0, new ApiError(422, 'bad'))).toBe(false);
  });

  it('never retries a GraphQL error about the request; retries an internal one once', () => {
    const bad = new GraphQLRequestError([{ message: 'x', extensions: { code: 'BAD_REQUEST' } }]);
    expect(shouldRetry(0, bad)).toBe(false);
    expect(shouldRetry(0, new GraphQLRequestError([{ message: 'boom' }]))).toBe(true);
  });

  it('retries a network failure or a 5xx once, then settles', () => {
    expect(shouldRetry(0, new TypeError('Failed to fetch'))).toBe(true);
    expect(shouldRetry(0, new ApiError(500, 'down'))).toBe(true);
    expect(shouldRetry(1, new ApiError(500, 'down'))).toBe(false);
  });

  it('retries a 503 (the API shedding load) several times, waiting as long as it asked', () => {
    const busy = new ApiError(503, 'busy', 2);
    expect(shouldRetry(4, busy)).toBe(true);
    expect(shouldRetry(5, busy)).toBe(false);
    expect(retryDelay(0, busy)).toBeGreaterThanOrEqual(2000);
    expect(retryDelay(0, busy)).toBeLessThan(2600);
    expect(retryDelay(3, busy)).toBeGreaterThan(retryDelay(0, busy));
    expect(retryDelay(20, busy)).toBeLessThanOrEqual(15_000);
  });
});

describe('createQueryClient', () => {
  it('is signed out by a sign-out with no page mounted yet, and forgets the cached data', () => {
    const client = createQueryClient(); // no component exists: the client alone listens
    client.setQueryData(['gql', 'Positions'], { rows: 1 });
    expect(signOuts.size).toBeGreaterThan(0);
    signOuts.forEach((signOut) => {
      signOut();
    });
    expect(client.getQueryData(['gql', 'Positions'])).toBeUndefined();
    expect(client.getQueryData(queryKeys.gql('Viewer', {}))).toBeNull();
  });
});
