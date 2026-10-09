/**
 * The cross-name event calendar over GraphQL (`Query.eventCalendar`, ADR 0037 / 0050): the next
 * 90 days of the names asked for (a screener's results) or of the site's scope list, one entry
 * per day, with the parts not known for the session.
 */
import { queryOptions, useQuery, type QueryClient } from '@tanstack/react-query';

import { gql, graphql, queryKeys, type gqlTypes } from '@/shared/api';

const EventCalendar = graphql(`
  query EventCalendar($instrumentIds: [String!]!, $scope: Boolean!) {
    eventCalendar(instrumentIds: $instrumentIds, scope: $scope) {
      session
      end
      names {
        instrumentId
        symbol
      }
      days {
        date
        isSession
        events {
          instrumentId
          symbol
          event {
            date
            time
            kind
            label
            name
            subjectId
            source
            knownFrom
            expiry
          }
        }
      }
      gaps {
        instrumentId
        part
        unknown {
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
      }
      missing
      unresolved
    }
  }
`);

export type EventCalendarResponse = NonNullable<gqlTypes.EventCalendarQuery['eventCalendar']>;

/**
 * The calendar of `instrumentIds` (empty with `scope`: the scope list alone); null: nothing
 * stored. `enabled` false waits for the ids (a screener's results still loading).
 */
export function useEventCalendar(instrumentIds: readonly string[], scope: boolean, enabled = true) {
  return useQuery({
    ...calendarQuery(instrumentIds, scope),
    select: (data: gqlTypes.EventCalendarQuery) => data.eventCalendar ?? null,
    enabled,
  });
}

function calendarQuery(instrumentIds: readonly string[], scope: boolean) {
  const variables = { instrumentIds: [...instrumentIds], scope };
  return queryOptions({
    queryKey: queryKeys.gql('EventCalendar', variables),
    queryFn: () => gql(EventCalendar, variables),
  });
}

/** Start reading the scope list's calendar (the page's default) before the page opens. */
export function prefetchCalendar(client: QueryClient): void {
  void client.query(calendarQuery([], true)).catch(() => undefined);
}
