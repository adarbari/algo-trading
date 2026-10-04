/** The TanStack Query client: one per app, with defaults for a read-mostly API. */
import { QueryClient } from '@tanstack/react-query';

import { ApiError } from '@/shared/api';

/** Retry a failed read once, but only when it may be transient: a 4xx answer (nothing stored,
 * a bad request) will not change, so it settles as an error at once instead of waiting. */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false;
  return failureCount < 1;
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { staleTime: 60_000, retry: shouldRetry, refetchOnWindowFocus: false },
    },
  });
}
