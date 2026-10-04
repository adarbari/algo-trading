/**
 * Trader > Ideas (home): the user's screeners in priority order beside the combined, ranked
 * list of top ideas across them. Tickers open in Explore (single, or a compare set).
 */
import { Grid, Stack, Text } from '@algotrade/ui';

import type { IdeaCompareSearch } from '@/features/idea-compare';
import { IdeasHeading } from '@/widgets/ideas-heading';
import { ScreenerRanking } from '@/widgets/screener-ranking';
import { TopIdeas } from '@/widgets/top-ideas';

export interface IdeasPageProps {
  /** Open the chosen tickers in Explore as a compare set. */
  onCompare: (search: IdeaCompareSearch) => void;
  /** Open one ticker in Explore. */
  onOpen: (symbol: string) => void;
  /** Open the screener Builder for a new screener. */
  onNewScreener: () => void;
}

export function IdeasPage({ onCompare, onOpen, onNewScreener }: IdeasPageProps) {
  return (
    <Stack gap={3}>
      <Stack gap={1}>
        <IdeasHeading />
        <Text size="sm" tone="secondary">
          Ranked by your screener priority, then score. Reorder the screeners to change the ranking.
        </Text>
      </Stack>
      <Grid columns="sidebar-start" gap={4} collapse="lg" align="start">
        <ScreenerRanking onNewScreener={onNewScreener} />
        <TopIdeas onCompare={onCompare} onOpen={onOpen} />
      </Grid>
    </Stack>
  );
}
