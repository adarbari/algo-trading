/**
 * The read hook for the text model's usage and cost over GraphQL (`Query.llmUsage`, Admin only;
 * ADR 0058, ADR 0037): windows with their caps, 30-day breakdowns, the daily series, reliability
 * and the latest calls. One operation serves the whole page, so every widget shares one request.
 */
import { useQuery } from '@tanstack/react-query';

import { gql, graphql, queryKeys } from '@/shared/api';

export const RECENT_CALLS = 50;

const LlmUsageQuery = graphql(`
  query LlmUsage($recent: Int!) {
    llmUsage(recent: $recent) {
      today
      recorded
      budget {
        dailyUsd
        monthlyUsd
        over
        reportedCallUsd
        error
      }
      windows {
        key
        start
        end
        cap {
          kind
          limitUsd
          usedShare
        }
        tally {
          calls
          inputTokens
          outputTokens
          callsWithoutTokens
          spentUsd
          billedUsd
          reportedUsd
          boundUsd
          freeCalls
          unknown {
            code
            kind
            guideTerm
            kindText
          }
        }
      }
      breakdowns {
        by
        rows {
          key
          provider
          costShare
          tally {
            calls
            inputTokens
            outputTokens
            callsWithoutTokens
            spentUsd
            billedUsd
            reportedUsd
            boundUsd
          }
        }
      }
      daily {
        day
        tally {
          calls
          inputTokens
          outputTokens
          spentUsd
          reportedUsd
          unknown {
            code
            kind
            guideTerm
            kindText
          }
        }
      }
      reliability {
        attempts
        ok
        fellBack
        failed
        skippedBudget
        fallbackRate
        failureRate
      }
      recent {
        ts
        provider
        model
        useCase
        user
        inputTokens
        outputTokens
        latencyS
        costUsd
        costBasis
        outcome
        fellBackFrom
        runId
        unknownFields
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
      }
    }
  }
`);

/** Null: the Admin read returned nothing (no stores). */
export function useLlmUsage(recent = RECENT_CALLS) {
  return useQuery({
    queryKey: queryKeys.gql('LlmUsage', { recent }),
    queryFn: () => gql(LlmUsageQuery, { recent }),
    select: (data) => data.llmUsage,
  });
}
