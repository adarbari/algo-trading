/**
 * The Ideas page's one read (ADR 0037): `IdeasPage` over GraphQL, the ranked ideas for the
 * latest session with every pick (the size each gets from the regime, ADR 0049), the picks the
 * regime gate paused with their reasons, the user's screeners with their run (or why not run) and
 * picked counts over the whole run, and each idea's facts by catalogue name (earnings, nearest
 * expiry, IV: ADR 0038). The cache holds the response; `select` shapes it.
 */
import { infiniteQueryOptions, useInfiniteQuery, type QueryClient } from '@tanstack/react-query';

import { gql, graphql, queryKeys } from '@/shared/api';

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
      priority
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
        regime
        sizeMultiplier
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
        picks {
          configId
          decision
          score
          reasons
          flags
          criteria {
            id
            outcome
            value
          }
          columns {
            name
            value
          }
        }
      }
    }
  }
`);

/**
 * The latest session's ideas (null `ideas`: nothing stored): the first page, and `fetchNextPage`
 * adds the next `IDEAS_PAGE` (the server's cursor, so no row twice and none missed). `select`
 * joins the pages into one `IdeasData`: the screeners and the paused picks are the first page's.
 */
export function useIdeas() {
  return useInfiniteQuery({ ...ideasQuery(), select: toPagedIdeas });
}

function toPagedIdeas(data: { pages: IdeasResponse[] }) {
  const first = data.pages[0]?.ideas;
  const last = data.pages.at(-1)?.ideas;
  if (!first || !last) return toIdeasData({ ideas: null });
  return toIdeasData({
    ideas: {
      ...first,
      items: data.pages.flatMap((page) => page.ideas?.items ?? []),
      total: last.total,
      hasMore: last.hasMore,
      nextCursor: last.nextCursor,
    },
  });
}

function ideasQuery() {
  const variables = { first: IDEAS_PAGE, names: [...IDEA_FEATURES] };
  return infiniteQueryOptions({
    queryKey: queryKeys.gql(IDEAS_OPERATION, variables),
    queryFn: ({ queryKey, pageParam }) =>
      gql(IdeasPage, { ...variables, after: pageParam }, queryKey),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.ideas?.nextCursor ?? null,
  });
}

/** Start the ideas read before the page mounts (a route loader); the hook then joins it. */
export function prefetchIdeas(client: QueryClient): void {
  void client.infiniteQuery(ideasQuery()).catch(() => undefined);
}
