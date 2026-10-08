/**
 * The user's train / test split (`Query.evaluationSplit`): their own `splitFrom` (null: none, so
 * each edge's frozen period is the split), the frozen periods of the edges they see and the
 * latest stored session a split may name. Written by `PUT /evaluation/split` (the
 * evaluation-split feature), which refreshes this read.
 */
import { useQuery, type QueryClient } from '@tanstack/react-query';

import { gql, graphql, queryKeys } from '@/shared/api';

const EvaluationSplit = graphql(`
  query EvaluationSplit {
    evaluationSplit {
      splitFrom
      latestSession
      frozenPeriods {
        edgeId
        frozenFrom
      }
    }
  }
`);

/** The split the user has saved and what it sits beside (null data: nothing stored yet). */
export function useEvaluationSplit() {
  return useQuery({
    queryKey: queryKeys.gql('EvaluationSplit', {}),
    queryFn: () => gql(EvaluationSplit, {}),
    select: (data) => data.evaluationSplit ?? null,
  });
}

/** Refetch the split after a save. */
export function refreshEvaluationSplit(client: QueryClient): Promise<void> {
  return client.invalidateQueries({ queryKey: queryKeys.gql('EvaluationSplit', {}) });
}
