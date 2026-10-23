/**
 * Events on the chart: one dated row per marker of the price chart above it, newest first,
 * over the chart's own range, with a chip per kind (counts, show / hide). A row links to its
 * source page where the server sent one (an 8-K's filing, a macro release's agency page).
 */
import { ChartEventList, Panel } from '@algotrade/ui';
import { useMemo } from 'react';

import { useChartEventRows } from '@/features/chart-events';
import { termHelp } from '@/features/guide-help';

export interface ChartEventListPanelProps {
  symbol: string;
  /** First day of the chart's range (ISO): the list follows the chart's range selector. */
  from: string;
}

export function ChartEventListPanel({ symbol, from }: ChartEventListPanelProps) {
  const found = useChartEventRows(symbol, from);
  const newestFirst = useMemo(() => [...found.events].reverse(), [found.events]);
  return (
    <Panel title="Events on the chart" actions={termHelp('chart_events')}>
      <ChartEventList
        label={`${symbol} events on the chart`}
        events={newestFirst}
        status={found.isError ? 'error' : found.isPending ? 'loading' : 'ready'}
        errorMessage={`${symbol} events failed to load.`}
        onRetry={found.refetch}
        emptyMessage={`No events on the ${symbol} chart in this range.`}
      />
    </Panel>
  );
}
