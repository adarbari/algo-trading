/**
 * Admin › Ingestion: completeness and quality of the data, high level first with ways to drill
 * down. The summary strip; the completeness grid beside the selected cell's drill-down; the
 * quality checks; verification vs IBKR beside the open review items; recent nightly runs. The
 * selected cell comes from the route (shareable); the page only lays the widgets out.
 */
import { Grid, Heading, Stack } from '@algotrade/ui';

import type { CellRef } from '@/entities/ingestion';
import { CompletenessPanel } from '@/widgets/completeness-panel';
import { DrilldownPanel } from '@/widgets/drilldown-panel';
import { IngestionSummary } from '@/widgets/ingestion-summary';
import { QualityChecksPanel } from '@/widgets/quality-checks-panel';
import { RecentRunsPanel } from '@/widgets/recent-runs-panel';
import { ReviewItemsPanel } from '@/widgets/review-items-panel';
import { VerificationPanel } from '@/widgets/verification-panel';

export interface AdminIngestionPageProps {
  /** The drilled-into cell (from the URL); none = the latest session's worst cell. */
  selected?: CellRef | null;
  onSelectCell: (cell: CellRef) => void;
}

export function AdminIngestionPage({ selected = null, onSelectCell }: AdminIngestionPageProps) {
  return (
    <Stack gap={4}>
      <Heading level={1}>Ingestion</Heading>
      <IngestionSummary />
      <Grid columns="main-aside" gap={4} collapse="lg" align="start">
        <CompletenessPanel selected={selected} onSelect={onSelectCell} />
        <DrilldownPanel selected={selected} />
      </Grid>
      <QualityChecksPanel />
      <Grid columns={2} gap={4} collapse="lg" align="start">
        <VerificationPanel />
        <ReviewItemsPanel />
      </Grid>
      <RecentRunsPanel />
    </Stack>
  );
}
