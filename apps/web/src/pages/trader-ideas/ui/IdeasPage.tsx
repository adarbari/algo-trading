/**
 * Trader > Ideas (home): the user's screeners in priority order beside the combined, ranked
 * list of top ideas across them. Tickers open in Explore (single, or a compare set).
 */
import { Grid, Heading, Stack, Text } from '@algotrade/ui';

import type { IdeaCompareSearch } from '@/features/idea-compare';
import { ScreenerRanking } from '@/widgets/screener-ranking';
import { TopIdeas } from '@/widgets/top-ideas';

export interface IdeasPageProps {
  /** Open the chosen tickers in Explore as a compare set. */
  onCompare: (search: IdeaCompareSearch) => void;
  /** Open one ticker in Explore. */
  onOpen: (symbol: string) => void;
}

export function IdeasPage({ onCompare, onOpen }: IdeasPageProps) {
  return (
    <Stack gap={3}>
      <Stack gap={1}>
        <Heading level={1}>Ideas</Heading>
        <Text size="sm" tone="secondary">
          Ranked by your screener priority, then score. Reorder the screeners to change the ranking.
        </Text>
      </Stack>
      <Grid columns="sidebar-start" gap={4} collapse="lg" align="start">
        <ScreenerRanking />
        <TopIdeas onCompare={onCompare} onOpen={onOpen} />
      </Grid>
    </Stack>
  );
}
