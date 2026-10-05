/**
 * "Your screeners": the user's screeners in priority order with what each found in its run
 * for the session (or that it did not run); drag to reorder (saved at once, the ideas re-rank).
 */
import { Button, Panel } from '@algotrade/ui';

import { ScreenerPriorityList } from '@/features/ideas-priority';
import { useIdeas } from '@/entities/idea';

export interface ScreenerRankingProps {
  /** Open the screener Builder for a new screener. */
  onNewScreener: () => void;
}

export function ScreenerRanking({ onNewScreener }: ScreenerRankingProps) {
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
      emptyMessage="You have no screeners yet. Create one to see its ideas here."
      errorMessage="The screeners failed to load."
      onRetry={() => void ideas.refetch()}
      footer={
        <Button variant="ghost" onClick={onNewScreener}>
          + New screener
        </Button>
      }
    >
      <ScreenerPriorityList screeners={screeners} />
    </Panel>
  );
}
