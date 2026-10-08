/**
 * "Your screeners": the user's screeners in priority order with what each found in its run
 * for the session (or that it did not run); drag to reorder (saved at once, the ideas re-rank).
 */
import { Button, Panel } from '@algotrade/ui';

import { ScreenerOdds } from '@/entities/edge';
import { useIdeas } from '@/entities/idea';
import { GuideHelp } from '@/features/guide-help';
import { ScreenerPriorityList } from '@/features/ideas-priority';

export interface ScreenerRankingProps {
  /** Open the screener Builder for a new screener. */
  onNewScreener: () => void;
  /** Open one screener's results (its name in the list). */
  onOpenScreener: (screenerId: string) => void;
}

export function ScreenerRanking({ onNewScreener, onOpenScreener }: ScreenerRankingProps) {
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
      <ScreenerPriorityList
        screeners={screeners}
        onOpenScreener={onOpenScreener}
        renderOdds={(id) => (
          <ScreenerOdds
            screenerId={id}
            info={<GuideHelp entry={{ kind: 'term', id: 'hit_rate' }} />}
          />
        )}
      />
    </Panel>
  );
}
