/**
 * The read hook for the text model's usage and cost over GraphQL (`Query.llmUsage`, Admin only;
 * ADR 0058, ADR 0037): windows with their caps, 30-day breakdowns, the daily series, reliability
 * the latest calls and the latest failures. One operation serves the whole page, so every widget shares one request.
 */
import { queryOptions, useQuery, type QueryClient } from '@tanstack/react-query';

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
          cacheReadTokens
          cacheWriteTokens
          totalInputTokens
          callsWithoutTotalInput
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
            cacheReadTokens
            cacheWriteTokens
            totalInputTokens
            callsWithoutTotalInput
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
          cacheReadTokens
          cacheWriteTokens
          totalInputTokens
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
        rejected
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
        cacheReadTokens
        cacheWriteTokens
        totalInputTokens
        latencyS
        costUsd
        costBasis
        outcome
        fellBackFrom
        runId
        error
        stage
        sentence
        answer
        promptChars
        callId
        promptVersion
        callStage
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
      failures {
        ts
        provider
        model
        useCase
        user
        inputTokens
        outputTokens
        cacheReadTokens
        cacheWriteTokens
        totalInputTokens
        latencyS
        costUsd
        costBasis
        outcome
        fellBackFrom
        runId
        error
        stage
        sentence
        answer
        promptChars
        callId
        promptVersion
        callStage
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

function llmUsageQuery(recent = RECENT_CALLS) {
  return queryOptions({
    queryKey: queryKeys.gql('LlmUsage', { recent }),
    queryFn: () => gql(LlmUsageQuery, { recent }),
  });
}

/** Start the read before the page mounts (a route loader); the hook then joins it. */
export function prefetchLlmUsage(client: QueryClient, recent = RECENT_CALLS): void {
  void client.query(llmUsageQuery(recent)).catch(() => undefined);
}

/** Null: the Admin read returned nothing (no stores). */
export function useLlmUsage(recent = RECENT_CALLS) {
  return useQuery({
    ...llmUsageQuery(recent),
    select: (data) => data.llmUsage,
  });
}
