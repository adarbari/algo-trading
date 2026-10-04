/**
 * Trader > Screeners > one screener (Builder): the draft bar, the criteria beside the run
 * summary and funnel, and the live preview's top rows. The widgets share the Builder's state
 * through its provider (a draft with its 300 ms debounced preview).
 */
import { Grid, Stack } from '@algotrade/ui';

import { ScreenerBuilderProvider } from '@/features/screener-builder';
import { CriteriaTable } from '@/widgets/criteria-table';
import { DraftBar } from '@/widgets/draft-bar';
import { PreviewResults } from '@/widgets/preview-results';
import { ScreenFunnel } from '@/widgets/screen-funnel';
import { ScreenSummary } from '@/widgets/screen-summary';

export interface ScreenerBuilderPageProps {
  /** The screener being built. */
  id: string;
  /** Open a ticker in Explore. */
  onOpenTicker: (symbol: string) => void;
}

export function ScreenerBuilderPage({ id, onOpenTicker }: ScreenerBuilderPageProps) {
  return (
    <ScreenerBuilderProvider id={id} key={id}>
      <Stack gap={3}>
        <DraftBar />
        <Grid columns="main-aside" gap={4} collapse="lg" align="start">
          <CriteriaTable />
          <Stack gap={3}>
            <ScreenSummary />
            <ScreenFunnel />
          </Stack>
        </Grid>
        <PreviewResults onOpen={onOpenTicker} />
      </Stack>
    </ScreenerBuilderProvider>
  );
}
