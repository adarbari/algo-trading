/**
 * Admin › Ingestion: completeness and quality of the data, high level first with ways to drill
 * down. The summary strip; the completeness grid beside the selected cell's drill-down; the
 * quality checks; verification vs IBKR beside the open review items (their rows open the ticker
 * in Explore); recent nightly runs. The
 * selected cell comes from the route (shareable); the page only lays the widgets out.
 */
import { Grid, Heading, MasterDetail, Stack } from '@algotrade/ui';

import { datasetLabel, type CellRef } from '@/entities/ingestion';
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
  /** Narrow only: the drill-down sheet was dismissed; the route clears the cell. */
  onClearCell: () => void;
  /** Open a ticker in Explore (a failing verification check or a review item). */
  onOpenTicker?: (symbol: string) => void;
}

export function AdminIngestionPage({
  selected = null,
  onSelectCell,
  onClearCell,
  onOpenTicker,
}: AdminIngestionPageProps) {
  return (
    <Stack gap={4}>
      <Heading level={1}>Ingestion</Heading>
      <IngestionSummary />
      <MasterDetail
        columns="main-aside"
        collapse="lg"
        master={<CompletenessPanel selected={selected} onSelect={onSelectCell} />}
        detail={<DrilldownPanel selected={selected} />}
        detailKey={selected ? `${selected.dataset}@${selected.session}` : null}
        detailTitle={selected ? `${datasetLabel(selected.dataset)} · ${selected.session}` : ''}
        onDetailClose={onClearCell}
      />
      <QualityChecksPanel />
      <Grid columns={2} gap={4} collapse="lg" align="start">
        <VerificationPanel {...(onOpenTicker ? { onOpen: onOpenTicker } : {})} />
        <ReviewItemsPanel {...(onOpenTicker ? { onOpen: onOpenTicker } : {})} />
      </Grid>
      <RecentRunsPanel />
    </Stack>
  );
}
