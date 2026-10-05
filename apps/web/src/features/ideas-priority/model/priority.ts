/**
 * The screener priority applied to a cached `IdeasPage` response (the optimistic update): the
 * screeners take the new order (the listed ones first, the rest after, as they were). The
 * ranking itself is the server's: the ideas re-rank when the saved order is refetched.
 */
import type { IdeasResponse } from '@/entities/idea';

export function withPriority(response: IdeasResponse, priority: readonly string[]): IdeasResponse {
  const ideas = response.ideas;
  if (!ideas) return response;
  const place = (id: string) => {
    const index = priority.indexOf(id);
    return index < 0 ? priority.length : index;
  };
  const screeners = [...ideas.screeners].sort(
    (a, b) => place(a.screener.id) - place(b.screener.id),
  );
  return { ...response, ideas: { ...ideas, priority: [...priority], screeners } };
}
