/**
 * Admin › Nightly run: the market-daily workflow, high level first with ways to drill down. The
 * summary strip stays above four views: Tonight (the run's steps, the quality checks, the
 * option-chain coverage), Data coverage (the completeness grid beside the selected cell's
 * drill-down, the fundamentals known against rows stored), Checks against IBKR, and the open
 * Review items (their rows open the ticker in Explore). The selected cell comes from the route
 * (shareable) and opens the coverage view; the page only lays the widgets out.
 */
import { Heading, MasterDetail, Stack, Tabs } from '@algotrade/ui';
import { useState } from 'react';

import { datasetLabel, type CellRef } from '@/entities/ingestion';
import { ChainCoveragePanel } from '@/widgets/chain-coverage-panel';
import { CompletenessPanel } from '@/widgets/completeness-panel';
import { DrilldownPanel } from '@/widgets/drilldown-panel';
import { IngestionSummary } from '@/widgets/ingestion-summary';
import { KnownCoveragePanel } from '@/widgets/known-coverage-panel';
import { QualityChecksPanel } from '@/widgets/quality-checks-panel';
import { RecentRunsPanel } from '@/widgets/recent-runs-panel';
import { ReviewItemsPanel } from '@/widgets/review-items-panel';
import { VerificationPanel } from '@/widgets/verification-panel';

const VIEWS = [
  { id: 'tonight', label: 'Tonight' },
  { id: 'coverage', label: 'Data coverage' },
  { id: 'verification', label: 'Checks against IBKR' },
  { id: 'review', label: 'Review items' },
] as const;

type View = (typeof VIEWS)[number]['id'];

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
  const [chosen, setView] = useState<View | null>(null);
  const view: View = chosen ?? (selected ? 'coverage' : 'tonight');
  const open = onOpenTicker ? { onOpen: onOpenTicker } : {};
  return (
    <Stack gap={4}>
      <Heading level={1}>Nightly run</Heading>
      <IngestionSummary />
      <Tabs
        items={VIEWS}
        value={view}
        onChange={(id) => {
          setView(id as View);
        }}
        label="Nightly run views"
      >
        {view === 'tonight' && (
          <Stack gap={4}>
            <RecentRunsPanel />
            <QualityChecksPanel />
            <ChainCoveragePanel />
          </Stack>
        )}
        {view === 'coverage' && (
          <Stack gap={4}>
            <MasterDetail
              columns="main-aside"
              collapse="lg"
              master={<CompletenessPanel selected={selected} onSelect={onSelectCell} />}
              detail={<DrilldownPanel selected={selected} />}
              detailKey={selected ? `${selected.dataset}@${selected.session}` : null}
              detailTitle={
                selected ? `${datasetLabel(selected.dataset)} · ${selected.session}` : ''
              }
              onDetailClose={onClearCell}
            />
            <KnownCoveragePanel />
          </Stack>
        )}
        {view === 'verification' && <VerificationPanel {...open} />}
        {view === 'review' && <ReviewItemsPanel {...open} />}
      </Tabs>
    </Stack>
  );
}
