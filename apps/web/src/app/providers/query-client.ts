/** The TanStack Query client: one per app, with defaults for a read-mostly API. */
import { QueryClient } from '@tanstack/react-query';

import { forgetUser } from '@/entities/viewer';
import { ApiError, GraphQLRequestError, onUnauthorized } from '@/shared/api';

/** GraphQL error codes about the request itself: asking again gets the same answer. */
const REQUEST_CODES = new Set(['BAD_REQUEST', 'NOT_FOUND', 'UNKNOWN_FEATURE']);

/** A 503 is the API shedding load, not a failure: retried quietly this many times, each after
 * the `Retry-After` it sent (or a growing backoff), before it shows as an error. */
const BUSY_RETRIES = 5;

/** The wait before retry number `failureCount`: for a 503 the server's `Retry-After`, growing
 * with each try; one second for the other failures (they are retried once). */
export function retryDelay(failureCount: number, error: unknown): number {
  if (!(error instanceof ApiError && error.status === 503)) return 1000;
  return (error.retryAfterS ?? 1) * 1000 * (1 + failureCount / 2);
}

/** Retry a failed read once, but only when it may be transient: a 4xx answer (nothing stored,
 * a bad request), or a GraphQL error about the request, will not change, so it settles as an
 * error at once instead of waiting. */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status === 503) return failureCount < BUSY_RETRIES;
  if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false;
  if (error instanceof GraphQLRequestError && error.codes.every((c) => REQUEST_CODES.has(c))) {
    return false;
  }
  return failureCount < 1;
}

/** One client per app. It is wired to the session here, before the router renders, so a
 * sign-out (another tab's, or the API refusing the token) can never arrive with nobody listening. */
export function createQueryClient(): QueryClient {
  const client = new QueryClient({
    defaultOptions: {
      queries: { staleTime: 60_000, retry: shouldRetry, retryDelay, refetchOnWindowFocus: false },
    },
  });
  onUnauthorized(() => {
    forgetUser(client);
  });
  return client;
}
