/**
 * The Ideas page's one read (ADR 0037): `IdeasPage` over GraphQL, the ideas for the latest
 * session ranked by the Ideas rule and served from each one's best pick (with the screeners that
 * picked it, the size it gets from the regime, ADR 0049), the picks the regime gate paused with
 * their reasons, the user's screeners with their run (or why not run) and picked counts over the
 * whole run, and each idea's facts by catalogue name (earnings, nearest expiry, IV: ADR 0038). The cache holds the response; `select` shapes it.
 */
import {
  queryOptions,
  useQueries,
  useQuery,
  useQueryClient,
  type QueryClient,
  type UseQueryResult,
} from '@tanstack/react-query';
import { useEffect } from 'react';

import { gql, GraphQLRequestError, graphql, queryKeys } from '@/shared/api';

import { IDEA_FEATURES } from '../model/facts';
import { toIdeasData, type IdeasResponse } from '../model/idea';

/** Ideas fetched per page: the first load and each "show more" (the API's default and half its maximum). */
export const IDEAS_PAGE = 50;

/** The GraphQL operation's name: its cached responses share this key prefix. */
export const IDEAS_OPERATION = 'IdeasPage';

const IdeasPage = graphql(`
  query IdeasPage($first: Int!, $after: String, $names: [FeatureName!]!) {
    ideas(first: $first, after: $after) {
      session
      total
      hasMore
      nextCursor
      pausedTotal
      paused {
        instrumentId
        instrument {
          symbol
        }
        result {
          configId
          score
          reasons
          regime
        }
      }
      screeners {
        screener {
          id
          name
          owner
          version
        }
        run {
          runId
          configVersion
          paused
        }
        notRun {
          code
          reason
          kind
          guideTerm
          kindText
          cause {
            links {
              level
              subject
              status
              message
              runId
            }
          }
        }
        picked
        withheld
        top {
          instrumentId
          score
          instrument {
            symbol
          }
        }
      }
      items {
        rank
        instrumentId
        score
        regime
        sizeMultiplier
        watchOut
        instrument {
          symbol
          name
          features(names: $names) {
            name
            value
            unknown {
              code
              kind
              guideTerm
              kindText
              cause {
                links {
                  level
                  subject
                  status
                  message
                  runId
                }
              }
            }
            info {
              format
              unit
              dtype
              nullMeaning
            }
          }
        }
        best {
          configId
          decision
          score
          reasons
          criteria {
            id
            outcome
          }
        }
        pickedBy {
          configId
          own
          position
          score
          decision
        }
        metrics {
          name
          value
        }
      }
    }
  }
`);

/** The cursors of the pages loaded after the first, in order (shared by every widget). */
const MORE_KEY = ['ideas-more'] as const;
const NO_CURSORS: readonly string[] = [];

/**
 * The latest session's ideas (null `ideas`: nothing stored): the first page, and `fetchNextPage`
 * adds the next `IDEAS_PAGE` by the server's cursor (so no row twice and none missed). One query
 * per page, keyed by its cursor; the cursors loaded so far live in the query cache, so every
 * widget reading the ideas shows the same pages. The pages join into one `IdeasData`: the
 * screeners and the paused picks are the first page's. (Not `useInfiniteQuery`: its observer
 * would sit in the entry's static graph, which is at its budget.)
 */
export function useIdeas() {
  const client = useQueryClient();
  const more = useQuery({
    queryKey: MORE_KEY,
    queryFn: () => NO_CURSORS,
    initialData: NO_CURSORS,
    staleTime: Infinity,
    gcTime: Infinity,
  });
  const cursors = more.data;
  const state = useQueries({
    queries: [null, ...cursors].map((after) => pageOptions(after)),
    combine: (results) => joinPages(results, cursors),
  });

  // A cursor the server refuses (BAD_REQUEST: the runs behind the loaded pages changed) means the
  // list is stale: start over from a fresh first page, never append to it.
  const { refused, keep, asked } = state;
  // Pages that no longer link up (see `linked`) leave the list for good: the cursors go with them.
  useEffect(() => {
    if (keep < asked) client.setQueryData(MORE_KEY, cursors.slice(0, keep - 1));
  }, [client, keep, asked, cursors]);
  useEffect(() => {
    if (refused) {
      client.setQueryData(MORE_KEY, NO_CURSORS);
      client.removeQueries({
        queryKey: queryKeys.gqlAll(IDEAS_OPERATION),
        predicate: (q) => 'after' in (q.queryKey[2] as object),
      });
      void client.resetQueries({ queryKey: pageOptions(null).queryKey, exact: true });
    }
  }, [client, refused]);

  const { next, laterFailed, refetchLater, refetchFirst } = state;
  return {
    data: state.data,
    error: state.error,
    isError: state.isError,
    isPending: state.isPending,
    isSuccess: state.isSuccess,
    isFetching: state.isFetching,
    refetch: () => {
      client.setQueryData(MORE_KEY, NO_CURSORS);
      return refetchFirst();
    },
    hasNextPage: next !== null,
    isFetchingNextPage: state.laterLoading,
    isFetchNextPageError: laterFailed,
    fetchNextPage: () => {
      if (laterFailed) return refetchLater();
      if (next !== null) client.setQueryData(MORE_KEY, [...cursors, next]);
      return Promise.resolve();
    },
  };
}

type PageResult = UseQueryResult<IdeasResponse>;

/**
 * How many leading pages still link up: page i stays only while page i-1 has data and its
 * `nextCursor` is the cursor page i was asked with. A refreshed first page over an older second
 * page, or a page that failed with later ones cached, breaks the chain there: the rest is never
 * shown, so a list has no gap and no stale tail.
 */
function linked(results: PageResult[], cursors: readonly string[]): number {
  let n = 1;
  while (n < results.length) {
    const before = results[n - 1]?.data?.ideas;
    if (!before || before.nextCursor !== cursors[n - 1]) break;
    n += 1;
  }
  return n;
}

/** The pages loaded so far as one state (the first page decides pending / error; the later ones
 * only whether the next page is loading or failed). Stable, so `useQueries` memoizes it. */
function joinPages(all: PageResult[], cursors: readonly string[]) {
  const keep = linked(all, cursors);
  const results = all.slice(0, keep);
  const [first, ...later] = results as [PageResult, ...PageResult[]];
  const last = later.at(-1);
  const pages = results.flatMap((r) => (r.data === undefined ? [] : [r.data]));
  return {
    data: first.data ? toPagedIdeas(pages) : undefined,
    error: first.error,
    isError: first.isError,
    isPending: first.isPending,
    isSuccess: first.isSuccess,
    isFetching: first.isFetching,
    keep,
    asked: all.length,
    next: pages.at(-1)?.ideas?.nextCursor ?? null,
    laterLoading: last !== undefined && last.isFetching && last.data === undefined,
    laterFailed: last?.isError === true,
    refused: last?.error instanceof GraphQLRequestError && last.error.codes.includes('BAD_REQUEST'),
    refetchFirst: () => first.refetch(),
    refetchLater: () => (last ?? first).refetch(),
  };
}

function toPagedIdeas(pages: IdeasResponse[]) {
  const first = pages[0]?.ideas;
  const last = pages.at(-1)?.ideas;
  if (!first || !last) return toIdeasData({ ideas: null });
  return toIdeasData({
    ideas: {
      ...first,
      items: pages.flatMap((page) => page.ideas?.items ?? []),
      total: last.total,
      hasMore: last.hasMore,
      nextCursor: last.nextCursor,
    },
  });
}

/** One page: the first (no cursor) keeps the key the page cache and the route prefetch know. */
function pageOptions(after: string | null) {
  const variables = { first: IDEAS_PAGE, names: [...IDEA_FEATURES] };
  return queryOptions({
    queryKey: queryKeys.gql(IDEAS_OPERATION, after === null ? variables : { ...variables, after }),
    queryFn: ({ queryKey }) => gql(IdeasPage, { ...variables, after }, queryKey),
  });
}

/** Start the ideas read before the page mounts (a route loader); the hook then joins it. */
export function prefetchIdeas(client: QueryClient): void {
  void client.query(pageOptions(null)).catch(() => undefined);
}
