/**
 * The rows of one ticker's event list under the price chart from `from` on (ISO day), oldest
 * first: the stored dividends, splits and earnings, the event study's own earnings and macro
 * dates ahead and its 8-K filings, each with its source page. Read through documents of their
 * own (not the chart's) so the chart's first load stays light; the same events the chart
 * marks, by the same rules, one row each.
 */
import type { ChartEvent } from '@algotrade/ui';
import { useMemo } from 'react';

import { useInstrumentEventList } from '../api/eventList';

import { storedEventRows } from './storedRows';
import { studyEventRows } from './studyRows';

export interface ChartEventRowsResult {
  /** Oldest first; empty until both reads have answered. */
  events: ChartEvent[];
  isPending: boolean;
  isError: boolean;
  refetch: () => void;
}

export function useChartEventRows(symbol: string, from: string): ChartEventRowsResult {
  const found = useInstrumentEventList(symbol);
  const stored = found.data?.events;
  const study = found.data?.eventStudy;
  const events = useMemo(() => {
    const marked = storedEventRows(stored ?? []);
    const earnings = new Set(marked.filter((e) => e.kind === 'earnings').map((e) => e.time));
    const studied = study ? studyEventRows(study, earnings) : [];
    return [...marked, ...studied]
      .filter((e) => e.time >= from)
      .sort((a, b) => a.time.localeCompare(b.time));
  }, [stored, study, from]);
  return {
    events,
    isPending: found.isPending,
    isError: found.isError,
    refetch: () => {
      void found.refetch();
    },
  };
}
