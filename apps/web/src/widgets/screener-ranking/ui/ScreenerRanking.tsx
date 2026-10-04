/**
 * "Your screeners": the user's screeners in priority order with what each found; drag to
 * reorder (saved at once, the ideas below re-rank).
 */
import { Panel } from '@algotrade/ui';

import { ScreenerPriorityList } from '@/features/ideas-priority';
import { useIdeas } from '@/entities/idea';

export function ScreenerRanking() {
  const ideas = useIdeas();
  const screeners = ideas.data?.screeners ?? [];
  const state =
    ideas.isError && !ideas.data
      ? 'error'
      : ideas.isPending
        ? 'loading'
        : screeners.length === 0
          ? 'empty'
          : 'ready';
  return (
    <Panel
      title="Your screeners"
      description="drag to reorder"
      state={state}
      loadingLabel="Loading screeners…"
      emptyMessage="No screener has picked anything yet. Finalise a screener to see its ideas here."
      errorMessage="The screeners failed to load."
      onRetry={() => void ideas.refetch()}
    >
      <ScreenerPriorityList screeners={screeners} />
    </Panel>
  );
}
