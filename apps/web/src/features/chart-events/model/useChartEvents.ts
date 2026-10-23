/**
 * The markers of one ticker's price chart from `from` on (ISO day), oldest first: the stored
 * dividends, splits and earnings, the event study's own earnings and macro dates ahead and its
 * 8-K filings, merged. The chart and the event list under it both read this, so a marker and
 * its row cannot disagree.
 */
import type { ChartEvent } from '@algotrade/ui';
import { useMemo } from 'react';

import { studyChartEvents, useInstrumentEventStudy } from '@/entities/event';
import { toChartEvents, useInstrumentEvents } from '@/entities/instrument';

export interface ChartEventsResult {
  /** Oldest first; empty until both reads have answered. */
  events: ChartEvent[];
  isPending: boolean;
  isError: boolean;
  refetch: () => void;
}

export function useChartEvents(symbol: string, from: string): ChartEventsResult {
  const stored = useInstrumentEvents(symbol);
  const study = useInstrumentEventStudy(symbol);
  const events = useMemo(() => {
    const marked = toChartEvents(stored.data ?? []);
    const earnings = new Set(marked.filter((e) => e.kind === 'earnings').map((e) => e.time));
    const studied = study.data ? studyChartEvents(study.data, earnings) : [];
    return [...marked, ...studied]
      .filter((e) => e.time >= from)
      .sort((a, b) => a.time.localeCompare(b.time));
  }, [stored.data, study.data, from]);
  return {
    events,
    isPending: stored.isPending || study.isPending,
    isError: stored.isError || study.isError,
    refetch: () => {
      void stored.refetch();
      void study.refetch();
    },
  };
}
