/**
 * The read hook for the event-study scope list over GraphQL (`Query.eventScope`, Admin only; ADR
 * 0050, ADR 0037): each name with its reasons, source, last deep-dive review, stale flag and the
 * share of its big moves attributed, the admin's removals, the symbols that did not resolve and
 * the macro calendar's reach. One operation serves the Admin Event scope page.
 */
import { useQuery, type QueryClient } from '@tanstack/react-query';

import { gql, graphql, queryKeys } from '@/shared/api';

const EventScopeQuery = graphql(`
  query EventScope {
    eventScope {
      session
      staleDays
      names {
        instrumentId
        symbol
        reasons
        source
        addedOn
        note
        by
        at
        lastReview
        stale
        moves {
          big
          attributed
          share
        }
      }
      removed {
        symbol
        by
        at
        note
        reasons
      }
      unresolved
      otherNames
      macroDays
      macroReleases
      macroUnknown {
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
  }
`);

/** Null: the Admin read returned nothing (no stores). */
export function useEventScope() {
  return useQuery({
    queryKey: queryKeys.gql('EventScope', {}),
    queryFn: ({ queryKey }) => gql(EventScopeQuery, {}, queryKey),
    select: (data) => data.eventScope,
  });
}

/** Read the list again (after an add or a removal; the Calendar's scope list reads it too). */
export function refreshEventScope(client: QueryClient): Promise<unknown> {
  return Promise.all([
    client.invalidateQueries({ queryKey: queryKeys.gqlAll('EventScope') }),
    client.invalidateQueries({ queryKey: queryKeys.gqlAll('EventCalendar') }),
  ]);
}
