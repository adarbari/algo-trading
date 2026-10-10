/**
 * Trader > Screeners > one screener (Builder): the draft bar, who an unsaved edit would add or
 * drop against the saved run, the regime gate in one line, the "Describe it" box (a sentence
 * to a draft, ADR 0041), the criteria beside the run summary and funnel, and the live preview's
 * top rows. The widgets share the Builder's state
 * through its provider (a draft with its 300 ms debounced preview).
 */
import { Grid, Stack } from '@algotrade/ui';

import { ScreenerBuilderProvider } from '@/features/screener-builder';
import { CriteriaTable } from '@/widgets/criteria-table';
import { DescribeScreen } from '@/widgets/describe-screen';
import { DraftBar } from '@/widgets/draft-bar';
import { PreviewResults } from '@/widgets/feature-table';
import { PreviewDiff } from '@/widgets/preview-diff';
import { RegimeGateLine } from '@/widgets/regime-gate';
import { ScreenFunnel } from '@/widgets/screen-funnel';
import { ScreenSummary } from '@/widgets/screen-summary';

export interface ScreenerBuilderPageProps {
  /** The screener being built. */
  id: string;
  /** Open a ticker in Explore. */
  onOpenTicker: (symbol: string) => void;
  /** The screener was deleted: back to the list. */
  onDeleted: () => void;
  /** Open the Regime page (the gate line's link). */
  onOpenRegime: () => void;
  /** Opened from an edge's builder: save and go back to it. */
  onReturn?: (() => void) | undefined;
}

export function ScreenerBuilderPage({
  id,
  onOpenTicker,
  onDeleted,
  onOpenRegime,
  onReturn,
}: ScreenerBuilderPageProps) {
  return (
    <ScreenerBuilderProvider id={id} key={id}>
      <Stack gap={3}>
        <DraftBar onDeleted={onDeleted} onReturn={onReturn} />
        <PreviewDiff />
        <RegimeGateLine screenerId={id} onOpenRegime={onOpenRegime} />
        <DescribeScreen />
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
