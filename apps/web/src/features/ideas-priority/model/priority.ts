/** The screener priority applied to a cached GET /ideas response (the optimistic update). */
import type { IdeasResponse } from '@/entities/idea';

export function withPriority(response: IdeasResponse, priority: readonly string[]): IdeasResponse {
  return { ...response, priority: [...priority] };
}
