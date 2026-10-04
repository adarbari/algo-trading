/** Read hook for the Ideas page: the ranked ideas and the user's screener priority. */
import { useQuery } from '@tanstack/react-query';

import { api, queryKeys, unwrap } from '@/shared/api';

import { toIdeasData } from '../model/idea';

/** Ideas fetched per load (the API's default is 50, its maximum 1000). */
export const IDEAS_LIMIT = 200;

/** The latest session's ideas; the cache holds the API response, `select` shapes it. */
export function useIdeas() {
  return useQuery({
    queryKey: queryKeys.ideas.top(IDEAS_LIMIT),
    queryFn: () => unwrap(api.GET('/ideas', { params: { query: { limit: IDEAS_LIMIT } } })),
    select: toIdeasData,
  });
}
